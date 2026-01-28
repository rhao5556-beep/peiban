"""
内容抓取 Celery 任务

定时任务：
1. fetch_daily_content - 每日内容抓取（7:00 AM）
2. cleanup_old_content - 清理旧内容（2:00 AM）
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import text

from app.worker import celery_app
from app.core.database import AsyncSessionLocal
from app.services.content_aggregator_service import ContentAggregatorService

logger = logging.getLogger(__name__)


def run_async(coro):
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


@celery_app.task(name="content.fetch_daily", bind=True, max_retries=3)
def fetch_daily_content(self):
    """
    每日内容抓取任务
    
    调度：每天 7:00 AM
    功能：从所有配置的来源抓取内容并保存到数据库
    """
    try:
        try:
            import redis
            from app.core.config import settings

            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
            acquired = r.set("locks:content:fetch_daily", datetime.utcnow().isoformat(), nx=True, ex=3 * 3600)
            if not acquired:
                return {"status": "skipped", "reason": "locked"}
        except Exception:
            pass
        return run_async(_fetch_daily_content_async())
    except Exception as e:
        logger.error(f"Daily content fetch failed: {e}")
        # 重试（指数退避）
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


async def _fetch_daily_content_async():
    """异步执行内容抓取"""
    logger.info("Starting daily content fetch...")
    start_time = datetime.now()
    
    async with AsyncSessionLocal() as db:
        aggregator = ContentAggregatorService(db)
        
        try:
            # 抓取所有来源
            contents = await aggregator.fetch_all_sources()
            
            # 批量保存
            saved_count = await aggregator.save_contents_batch(contents)
            
            elapsed = (datetime.now() - start_time).total_seconds()
            
            logger.info(
                f"Daily content fetch complete: "
                f"fetched={len(contents)}, saved={saved_count}, "
                f"elapsed={elapsed:.2f}s"
            )
            
            # 更新 Prometheus 指标（如果已配置）
            try:
                from prometheus_client import Counter, Histogram
                
                content_fetch_total = Counter(
                    'content_fetch_total',
                    'Total number of contents fetched',
                    ['source']
                )
                
                content_fetch_duration = Histogram(
                    'content_fetch_duration_seconds',
                    'Time spent fetching content'
                )
                
                # 按来源统计
                for content in contents:
                    content_fetch_total.labels(source=content.source).inc()
                
                content_fetch_duration.observe(elapsed)
                
            except Exception as e:
                logger.warning(f"Failed to update metrics: {e}")
            
            return {
                "status": "success",
                "fetched": len(contents),
                "saved": saved_count,
                "elapsed_seconds": elapsed,
                "timestamp": datetime.now().isoformat()
            }
            
        finally:
            await aggregator.close()


@celery_app.task(name="content.cleanup_old", bind=True, max_retries=3)
def cleanup_old_content(self):
    """
    清理旧内容任务
    
    调度：每天 2:00 AM
    保留策略：7 天内的内容
    """
    try:
        try:
            import redis
            from app.core.config import settings

            r = redis.from_url(settings.REDIS_URL, decode_responses=True)
            acquired = r.set("locks:content:cleanup_old", datetime.utcnow().isoformat(), nx=True, ex=3 * 3600)
            if not acquired:
                return {"status": "skipped", "reason": "locked"}
        except Exception:
            pass
        return run_async(_cleanup_old_content_async())
    except Exception as e:
        logger.error(f"Content cleanup failed: {e}")
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))


async def _cleanup_old_content_async():
    """异步执行清理"""
    logger.info("Starting old content cleanup...")
    
    cutoff_date = datetime.now() - timedelta(days=7)
    
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                text("""
                    UPDATE content_library
                    SET is_active = FALSE
                    WHERE fetched_at < :cutoff_date
                      AND is_active = TRUE
                    RETURNING id
                """),
                {"cutoff_date": cutoff_date}
            )
            await db.commit()
            
            deleted_ids = result.fetchall()
            count = len(deleted_ids)
            
            logger.info(f"Archived {count} old contents (older than {cutoff_date})")
            
            return {
                "status": "success",
                "archived": count,
                "cutoff_date": cutoff_date.isoformat(),
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            await db.rollback()
            logger.error(f"Failed to cleanup old content: {e}")
            raise


@celery_app.task(name="content.test_fetch", bind=True)
def test_fetch_content(self):
    """
    测试内容抓取任务（手动触发）
    
    用于测试和调试，不会自动调度
    """
    try:
        return run_async(_test_fetch_content_async())
    except Exception as e:
        logger.error(f"Test fetch failed: {e}")
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }


async def _test_fetch_content_async():
    """测试抓取（只抓取 RSS）"""
    logger.info("Starting test content fetch (RSS only)...")
    
    async with AsyncSessionLocal() as db:
        aggregator = ContentAggregatorService(db)
        
        try:
            # 只抓取 RSS
            contents = await aggregator.fetch_rss_feeds()
            
            logger.info(f"Test fetch complete: {len(contents)} contents")
            
            # 返回前 5 条内容的摘要
            sample = [
                {
                    "title": c.title,
                    "source": c.source,
                    "url": c.content_url,
                    "tags": c.tags
                }
                for c in contents[:5]
            ]
            
            return {
                "status": "success",
                "total": len(contents),
                "sample": sample,
                "timestamp": datetime.now().isoformat()
            }
            
        finally:
            await aggregator.close()
