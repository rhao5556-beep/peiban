"""Celery Worker 模块"""
from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_shutdown
from app.core.config import settings

# 创建 Celery 应用
celery_app = Celery(
    "affinity",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "app.worker.tasks.outbox",
        "app.worker.tasks.decay",
        "app.worker.tasks.deletion",
        "app.worker.tasks.consistency",
        "app.worker.tasks.content_aggregation",  # 内容抓取任务
        "app.worker.tasks.content_recommendation",  # 推荐生成任务
        "app.worker.tasks.meme_aggregation"  # 表情包聚合任务
    ]
)

# Celery 配置
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,  # 5 minutes
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Celery Beat 定时任务配置
celery_app.conf.beat_schedule = {
    # 每日凌晨3点执行边权重批量更新
    "daily_decay_update": {
        "task": "app.worker.tasks.decay.batch_update_edge_weights",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "low_priority"}
    },
    
    # 每小时执行数据一致性检查
    "hourly_consistency_check": {
        "task": "app.worker.tasks.consistency.check_data_consistency",
        "schedule": crontab(minute=0),
        "options": {"queue": "maintenance"}
    },
    
    # 每6小时执行GDPR物理删除
    "gdpr_physical_delete": {
        "task": "app.worker.tasks.deletion.execute_physical_deletion",
        "schedule": crontab(minute=0, hour="*/6"),
        "options": {"queue": "high_priority"}
    },
    
    # 每30秒处理Outbox积压（加快记忆状态更新）
    "outbox_processor": {
        "task": "app.worker.tasks.outbox.process_pending_events",
        "schedule": 30,  # 30 seconds
        "options": {"queue": "default"}
    },

    "outbox_requeue_stuck_processing": {
        "task": "app.worker.tasks.outbox.requeue_stuck_processing_events",
        "schedule": 60,
        "options": {"queue": "maintenance"}
    },

    "outbox_reconcile_incomplete": {
        "task": "app.worker.tasks.outbox.reconcile_incomplete_outbox_events",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "maintenance"}
    },
    
    # 每小时清理过期幂等键
    "cleanup_idempotency_keys": {
        "task": "app.worker.tasks.consistency.cleanup_expired_keys",
        "schedule": crontab(minute=10),
        "options": {"queue": "maintenance"}
    },

    "celerybeat_heartbeat": {
        "task": "consistency.beat_heartbeat",
        "schedule": 30,
        "options": {"queue": "maintenance"}
    },

    "daily_session_cleanup": {
        "task": "consistency.cleanup_stale_sessions",
        "schedule": crontab(hour=4, minute=30),
        "options": {"queue": "maintenance"}
    },
    
    # 每日 7:00 AM 抓取内容
    "daily_content_fetch": {
        "task": "content.fetch_daily",
        "schedule": crontab(hour=7, minute=0),
        "options": {"queue": "content"}
    },
    
    # 每日 2:00 AM 清理旧内容
    "daily_content_cleanup": {
        "task": "content.cleanup_old",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "maintenance"}
    },
    
    # 每日 9:00 AM 生成推荐
    "daily_recommendation_generation": {
        "task": "content.generate_recommendations",
        "schedule": crontab(hour=9, minute=0),
        "options": {"queue": "content"}
    },
    
    # 每小时聚合热点表情包（MVP：微博）
    "hourly_meme_aggregation": {
        "task": "meme.aggregate_trending_memes",
        "schedule": crontab(minute=0),
        "options": {"queue": "meme"}
    },
    
    # 每2小时更新表情包趋势分数
    "meme_score_update": {
        "task": "meme.update_meme_scores",
        "schedule": crontab(minute=0, hour="*/2"),
        "options": {"queue": "meme"}
    },
    
    # 每日归档旧表情包
    "daily_meme_archival": {
        "task": "meme.archive_old_memes",
        "schedule": crontab(hour=4, minute=0),
        "options": {"queue": "maintenance"}
    }
}

# 队列路由
celery_app.conf.task_routes = {
    "app.worker.tasks.outbox.*": {"queue": "default"},
    "app.worker.tasks.decay.*": {"queue": "low_priority"},
    "app.worker.tasks.deletion.*": {"queue": "high_priority"},
    "app.worker.tasks.consistency.*": {"queue": "maintenance"},
    "content.*": {"queue": "content"},  # 内容推荐任务队列
    "meme.*": {"queue": "meme"},  # 表情包任务队列
}


@worker_process_shutdown.connect
def _close_worker_resources(**kwargs):
    try:
        from app.worker.tasks.outbox import close_sync_neo4j_driver as close_outbox_driver
        close_outbox_driver()
    except Exception:
        pass
    try:
        from app.worker.tasks.decay import close_sync_neo4j_driver as close_decay_driver
        close_decay_driver()
    except Exception:
        pass
