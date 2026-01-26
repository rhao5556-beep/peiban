"""
手动触发内容聚合任务
从真实来源抓取今日热点内容
"""
import asyncio
import logging
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.services.content_aggregator_service import ContentAggregatorService

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("开始抓取今日热点内容...")
    logger.info("=" * 60)
    
    # 创建数据库连接
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # 创建聚合服务
        aggregator = ContentAggregatorService(db)
        
        try:
            # 抓取所有来源
            logger.info("\n📡 正在从以下来源抓取内容：")
            logger.info("  - RSS 订阅（36氪、IT之家、极客公园等）")
            logger.info("  - 微博热搜")
            logger.info("  - 知乎热榜")
            logger.info("  - B站热门")
            logger.info("")
            
            contents = await aggregator.fetch_all_sources()
            
            logger.info(f"\n✅ 抓取完成！共获取 {len(contents)} 条内容")
            
            # 保存到数据库
            logger.info("\n💾 正在保存到数据库...")
            saved_count = await aggregator.save_contents_batch(contents)
            
            logger.info(f"\n✅ 保存完成！成功保存 {saved_count} 条新内容")
            
            # 显示部分内容预览
            if contents:
                logger.info("\n📰 内容预览（前5条）：")
                for i, content in enumerate(contents[:5], 1):
                    logger.info(f"\n{i}. [{content.source}] {content.title}")
                    if content.summary:
                        logger.info(f"   摘要: {content.summary[:100]}...")
                    logger.info(f"   链接: {content.content_url}")
            
            logger.info("\n" + "=" * 60)
            logger.info("✅ 内容聚合任务完成！")
            logger.info("=" * 60)
            
        except Exception as e:
            logger.error(f"\n❌ 任务失败: {e}", exc_info=True)
        finally:
            await aggregator.close()
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
