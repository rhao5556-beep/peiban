"""表情包聚合和管理的 Celery 任务"""
import logging
from datetime import datetime, timedelta
from typing import List

from app.worker import celery_app
from app.services.trending_content_sensor_service import TrendingContentSensorService
from app.services.content_pool_manager_service import ContentPoolManagerService
from app.services.safety_screener_service import SafetyScreenerService
from app.services.trend_analyzer_service import TrendAnalyzerService
from app.core.database import AsyncSessionLocal
from app.core.config import settings

logger = logging.getLogger(__name__)


@celery_app.task(name="meme.aggregate_trending_memes", bind=True, max_retries=3)
def aggregate_trending_memes(self):
    """
    聚合热点表情包内容的 Celery 任务
    
    流程：
    1. 从外部平台获取热点内容（MVP：仅微博）
    2. 计算 content_hash 并检查重复
    3. 创建候选表情包记录
    4. 运行安全筛选
    5. 根据筛选结果更新状态
    6. 计算初始趋势分数
    
    计划：每 1 小时运行一次（MVP：微博 API 允许此频率）
    """
    import asyncio
    
    async def _aggregate():
        start_time = datetime.now()
        logger.info("Starting meme aggregation task")

        try:
            from app.core.database import redis_client
            import redis.asyncio as redis
            r = redis_client or redis.from_url(settings.REDIS_URL, decode_responses=True)
            lock_key = "locks:meme:aggregate_trending_memes"
            acquired = await r.set(lock_key, str(start_time.timestamp()), nx=True, ex=3600)
            if not acquired:
                logger.info("Meme aggregation skipped due to existing distributed lock")
                return {"success": True, "skipped": True, "reason": "locked"}
        except Exception:
            pass
        
        # 统计指标
        total_fetched = 0
        duplicates_detected = 0
        created_count = 0
        approved_count = 0
        rejected_count = 0
        flagged_count = 0
        
        try:
            async with AsyncSessionLocal() as db:
                # 初始化服务
                sensor_service = TrendingContentSensorService()
                pool_manager = ContentPoolManagerService(db)
                safety_screener = SafetyScreenerService()
                trend_analyzer = TrendAnalyzerService(db)
                
                # 1. 从平台获取热点内容
                meme_candidates = await sensor_service.aggregate_all_trends()
                total_fetched = len(meme_candidates)
                logger.info(f"Fetched {total_fetched} meme candidates from platforms")
                
                # 2. 处理每个候选表情包
                for candidate in meme_candidates:
                    try:
                        # 检查重复（通过 content_hash）
                        is_duplicate = await pool_manager.check_duplicate(candidate["content_hash"])
                        
                        if is_duplicate:
                            duplicates_detected += 1
                            logger.debug(f"Duplicate meme detected: {candidate['content_hash'][:16]}")
                            continue
                        
                        # 创建候选记录
                        meme = await pool_manager.create_meme_candidate(
                            text_description=candidate["text_description"],
                            source_platform=candidate["source_platform"],
                            content_hash=candidate["content_hash"],
                            image_url=candidate.get("image_url"),
                            category=candidate.get("category"),
                            popularity_score=candidate.get("popularity_score", 0.0),
                            original_source_url=candidate.get("original_source_url")
                        )
                        created_count += 1
                        logger.info(f"Created meme candidate: {meme.id}")
                        
                        # 3. 运行安全筛选
                        screening_result = await safety_screener.screen_meme(meme)
                        
                        # 4. 根据筛选结果更新状态
                        if screening_result.overall_status == "approved":
                            await pool_manager.update_meme_status(
                                meme.id, "approved", 
                                safety_status="approved",
                                safety_check_details=screening_result.to_dict()
                            )
                            approved_count += 1
                            
                            # 5. 计算初始趋势分数
                            trend_score = await trend_analyzer.calculate_trend_score(meme)
                            trend_level = trend_analyzer.determine_trend_level(trend_score)
                            
                            await pool_manager.update_meme_trend(
                                meme.id, trend_score, trend_level
                            )
                            
                            logger.info(
                                f"Approved meme {meme.id}: score={trend_score:.2f}, level={trend_level}"
                            )
                            
                        elif screening_result.overall_status == "rejected":
                            await pool_manager.update_meme_status(
                                meme.id, "rejected",
                                safety_status="rejected",
                                safety_check_details=screening_result.to_dict()
                            )
                            rejected_count += 1
                            logger.warning(f"Rejected meme {meme.id}: {screening_result.rejection_reason}")
                            
                        else:  # flagged
                            await pool_manager.update_meme_status(
                                meme.id, "flagged",
                                safety_status="flagged",
                                safety_check_details=screening_result.to_dict()
                            )
                            flagged_count += 1
                            logger.warning(f"Flagged meme {meme.id} for manual review")
                        
                    except Exception as e:
                        logger.error(f"Error processing meme candidate: {e}", exc_info=True)
                        continue
            
            # 记录统计信息
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Meme aggregation completed in {duration:.2f}s: "
                f"fetched={total_fetched}, duplicates={duplicates_detected}, "
                f"created={created_count}, approved={approved_count}, "
                f"rejected={rejected_count}, flagged={flagged_count}"
            )
            
            return {
                "success": True,
                "total_fetched": total_fetched,
                "duplicates_detected": duplicates_detected,
                "created": created_count,
                "approved": approved_count,
                "rejected": rejected_count,
                "flagged": flagged_count,
                "duration_seconds": duration
            }
            
        except Exception as e:
            logger.error(f"Meme aggregation task failed: {e}", exc_info=True)
            # 重试任务
            raise self.retry(exc=e, countdown=300)  # 5 分钟后重试
    
    # 运行异步任务
    return asyncio.run(_aggregate())


@celery_app.task(name="meme.update_meme_scores", bind=True, max_retries=3)
def update_meme_scores(self):
    """
    更新所有活跃表情包的趋势分数
    
    流程：
    1. 重新计算所有活跃表情包的趋势分数
    2. 根据新分数更新 trend_level
    3. 识别衰退表情包（分数 < 30 持续 7+ 天）
    
    计划：每 2 小时运行一次（目标：< 2 小时检测延迟）
    """
    import asyncio
    
    async def _update_scores():
        start_time = datetime.now()
        logger.info("Starting meme score update task")
        
        # 统计指标
        updated_count = 0
        declining_count = 0
        
        try:
            async with AsyncSessionLocal() as db:
                # 初始化服务
                trend_analyzer = TrendAnalyzerService(db)
                pool_manager = ContentPoolManagerService(db)
                
                # 1. 更新所有活跃表情包的分数
                updated_memes = await trend_analyzer.update_all_trend_scores()
                updated_count = len(updated_memes)
                logger.info(f"Updated trend scores for {updated_count} memes")
                
                # 2. 识别衰退表情包
                declining_memes = await trend_analyzer.identify_declining_memes()
                declining_count = len(declining_memes)
                
                if declining_count > 0:
                    logger.info(f"Identified {declining_count} declining memes")
                    
                    # 更新衰退表情包的 trend_level
                    for meme in declining_memes:
                        await pool_manager.update_meme_trend(
                            meme.id, meme.trend_score, "declining"
                        )
            
            # 记录统计信息
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Meme score update completed in {duration:.2f}s: "
                f"updated={updated_count}, declining={declining_count}"
            )
            
            return {
                "success": True,
                "updated": updated_count,
                "declining": declining_count,
                "duration_seconds": duration
            }
            
        except Exception as e:
            logger.error(f"Meme score update task failed: {e}", exc_info=True)
            # 重试任务
            raise self.retry(exc=e, countdown=600)  # 10 分钟后重试
    
    # 运行异步任务
    return asyncio.run(_update_scores())


@celery_app.task(name="meme.archive_old_memes", bind=True, max_retries=3)
def archive_old_memes(self):
    """
    归档旧的衰退表情包
    
    流程：
    1. 查找符合归档条件的表情包（衰退 > 30 天）
    2. 将状态更新为"已归档"
    
    计划：每日运行
    """
    import asyncio
    
    async def _archive():
        start_time = datetime.now()
        logger.info("Starting meme archival task")
        
        # 统计指标
        archived_count = 0
        
        try:
            async with AsyncSessionLocal() as db:
                # 初始化服务
                pool_manager = ContentPoolManagerService(db)
                
                # 1. 获取符合归档条件的表情包
                memes_to_archive = await pool_manager.get_memes_for_archival()
                logger.info(f"Found {len(memes_to_archive)} memes eligible for archival")
                
                # 2. 归档每个表情包
                for meme in memes_to_archive:
                    try:
                        await pool_manager.archive_meme(meme.id)
                        archived_count += 1
                        logger.info(f"Archived meme {meme.id}")
                    except Exception as e:
                        logger.error(f"Error archiving meme {meme.id}: {e}")
                        continue
            
            # 记录统计信息
            duration = (datetime.now() - start_time).total_seconds()
            logger.info(
                f"Meme archival completed in {duration:.2f}s: archived={archived_count}"
            )
            
            return {
                "success": True,
                "archived": archived_count,
                "duration_seconds": duration
            }
            
        except Exception as e:
            logger.error(f"Meme archival task failed: {e}", exc_info=True)
            # 重试任务
            raise self.retry(exc=e, countdown=3600)  # 1 小时后重试
    
    # 运行异步任务
    return asyncio.run(_archive())
