"""
推荐生成 Celery 任务

定时任务：
1. generate_daily_recommendations - 每日推荐生成（9:00 AM）
"""
import asyncio
import logging
from datetime import datetime
from sqlalchemy import text

from app.worker import celery_app
from app.core.database import AsyncSessionLocal, get_neo4j_driver
from app.services.content_recommendation_service import ContentRecommendationService

logger = logging.getLogger(__name__)


def run_async(coro):
    """
    统一的异步任务执行器，避免事件循环冲突
    """
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@celery_app.task(name="content.generate_recommendations", bind=True, max_retries=3)
def generate_daily_recommendations(self):
    """
    每日推荐生成任务
    
    调度：每天 9:00 AM
    功能：为所有启用推荐的 friend+ 用户生成推荐
    """
    try:
        return run_async(_generate_daily_recommendations_async())
    except Exception as e:
        logger.error(f"Daily recommendation generation failed: {e}")
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


async def _generate_daily_recommendations_async():
    """异步执行推荐生成"""
    logger.info("Starting daily recommendation generation...")
    start_time = datetime.now()
    
    # 获取 Neo4j 驱动
    neo4j_driver = get_neo4j_driver()
    
    async with AsyncSessionLocal() as db:
        try:
            # 获取所有启用推荐的用户（friend+ 状态）
            result = await db.execute(
                text("""
                    SELECT DISTINCT u.id, a.state as affinity_state
                    FROM users u
                    JOIN user_content_preference p ON u.id = p.user_id
                    JOIN affinity_scores a ON u.id = a.user_id
                    WHERE p.content_recommendation_enabled = TRUE
                      AND a.state IN ('friend', 'close_friend')
                """)
            )
            
            users = result.fetchall()
            logger.info(f"Found {len(users)} users eligible for recommendations")
            
            if not users:
                return {
                    "status": "success",
                    "users_processed": 0,
                    "success": 0,
                    "message": "No eligible users found",
                    "timestamp": datetime.now().isoformat()
                }
            
            # 为每个用户生成推荐
            recommendation_service = ContentRecommendationService(db, neo4j_driver)
            
            success_count = 0
            failed_users = []
            
            for user in users:
                user_id = str(user[0])
                affinity_state = user[1]
                
                try:
                    # 生成推荐
                    recommendations = await recommendation_service.generate_recommendations(
                        user_id=user_id,
                        top_k=3
                    )
                    
                    if recommendations:
                        success_count += 1
                        logger.info(
                            f"Generated {len(recommendations)} recommendations "
                            f"for user {user_id} (state: {affinity_state})"
                        )
                    else:
                        logger.info(f"No recommendations generated for user {user_id}")
                    
                    # 更新 Prometheus 指标（如果已配置）
                    try:
                        from prometheus_client import Counter
                        
                        recommendation_delivered_total = Counter(
                            'recommendation_delivered_total',
                            'Total number of recommendations delivered'
                        )
                        
                        if recommendations:
                            recommendation_delivered_total.inc(len(recommendations))
                    except Exception as e:
                        logger.warning(f"Failed to update metrics: {e}")
                    
                except Exception as e:
                    logger.error(f"Failed to generate recommendation for user {user_id}: {e}")
                    failed_users.append(user_id)
                    
                    # 更新错误指标
                    try:
                        from prometheus_client import Counter
                        
                        recommendation_errors_total = Counter(
                            'recommendation_errors_total',
                            'Total number of recommendation errors'
                        )
                        
                        recommendation_errors_total.inc()
                    except:
                        pass
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                f"Daily recommendation generation complete: "
                f"users_processed={len(users)}, success={success_count}, "
                f"failed={len(failed_users)}, elapsed={elapsed:.2f}s"
            )
            
            # 更新总体指标
            try:
                from prometheus_client import Counter, Histogram
                
                recommendation_generation_total = Counter(
                    'recommendation_generation_total',
                    'Total number of recommendation batches generated'
                )
                
                recommendation_generation_duration = Histogram(
                    'recommendation_generation_duration_seconds',
                    'Time spent generating recommendations'
                )
                
                recommendation_generation_total.inc(success_count)
                recommendation_generation_duration.observe(elapsed)
            except:
                pass
            
            return {
                "status": "success",
                "users_processed": len(users),
                "success": success_count,
                "failed": len(failed_users),
                "failed_users": failed_users[:10],  # 只返回前10个失败用户
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to generate daily recommendations: {e}")
            raise


@celery_app.task(name="content.test_recommendation", bind=True)
def test_recommendation_for_user(self, user_id: str):
    """
    测试推荐生成（手动触发）
    
    Args:
        user_id: 用户 ID
    """
    try:
        return run_async(_test_recommendation_async(user_id))
    except Exception as e:
        logger.error(f"Test recommendation failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def _test_recommendation_async(user_id: str):
    """测试单个用户的推荐生成"""
    logger.info(f"Testing recommendation generation for user {user_id}")
    
    neo4j_driver = get_neo4j_driver()
    
    async with AsyncSessionLocal() as db:
        recommendation_service = ContentRecommendationService(db, neo4j_driver)
        
        try:
            recommendations = await recommendation_service.generate_recommendations(
                user_id=user_id,
                top_k=3
            )
            
            # 返回推荐摘要
            result = {
                "status": "success",
                "user_id": user_id,
                "count": len(recommendations),
                "recommendations": [
                    {
                        "title": rec.content.title,
                        "source": rec.content.source,
                        "url": rec.content.content_url,
                        "score": rec.match_score,
                        "rank": rec.rank_position
                    }
                    for rec in recommendations
                ],
                "timestamp": datetime.now().isoformat()
            }
            
            logger.info(f"Test recommendation complete: {len(recommendations)} recommendations")
            return result
            
        except Exception as e:
            logger.error(f"Test recommendation failed: {e}")
            raise
