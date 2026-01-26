"""
插入真实的热点内容数据（模拟抓取结果）
用于快速测试推荐功能
"""
import asyncio
from datetime import datetime
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

# 使用容器网络中的数据库 URL
DATABASE_URL = "postgresql+asyncpg://affinity:affinity_secret@affinity-postgres:5432/affinity"

# 今日热点内容（真实示例）
SAMPLE_CONTENTS = [
    {
        "source": "zhihu",
        "title": "2026年AI技术发展趋势：大模型进入应用落地阶段",
        "summary": "随着GPT-4、Claude等大模型的成熟，2026年AI应用将从实验室走向千行百业。本文分析了AI Agent、多模态、端侧部署等关键趋势。",
        "url": "https://www.zhihu.com/question/12345678",
        "tags": ["AI", "技术", "趋势"],
    },
    {
        "source": "weibo",
        "title": "春节档电影预售破10亿，《流浪地球3》领跑",
        "summary": "2026年春节档电影预售火爆，《流浪地球3》以超高口碑领跑，科幻题材持续受到观众喜爱。",
        "url": "https://weibo.com/1234567890/abcdefg",
        "tags": ["电影", "春节", "娱乐"],
    },
    {
        "source": "bilibili",
        "title": "【技术分享】从零搭建个人AI助手：GraphRAG实战",
        "summary": "本视频详细讲解如何使用Neo4j和向量数据库构建具有长期记忆的AI助手，包含完整代码和部署指南。",
        "url": "https://www.bilibili.com/video/BV1234567890",
        "tags": ["技术", "AI", "教程"],
    },
    {
        "source": "zhihu",
        "title": "如何看待2026年房地产市场回暖？",
        "summary": "多地出台楼市新政，一线城市成交量回升。专家分析认为市场正在筑底，但仍需关注经济基本面变化。",
        "url": "https://www.zhihu.com/question/23456789",
        "tags": ["房产", "经济", "投资"],
    },
    {
        "source": "bilibili",
        "title": "【美食】春节必备！10道硬菜教程合集",
        "summary": "春节将至，为大家准备了10道拿手硬菜的详细教程，包括红烧肉、糖醋排骨、清蒸鱼等经典菜品。",
        "url": "https://www.bilibili.com/video/BV2345678901",
        "tags": ["美食", "春节", "教程"],
    },
]


async def main():
    print("=" * 60)
    print("开始插入真实热点内容...")
    print("=" * 60)
    
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        inserted_count = 0
        
        for content in SAMPLE_CONTENTS:
            try:
                # 检查是否已存在
                result = await db.execute(
                    text("SELECT id FROM content_library WHERE content_url = :url"),
                    {"url": content["url"]}
                )
                
                if result.scalar_one_or_none():
                    print(f"⏭️  已存在: {content['title']}")
                    continue
                
                # 插入新内容（不包含 embedding，让推荐服务生成）
                await db.execute(
                    text("""
                        INSERT INTO content_library (
                            source, source_url, title, summary, content_url, tags,
                            published_at, quality_score
                        ) VALUES (
                            :source, :source_url, :title, :summary, :url, :tags,
                            :published_at, :quality_score
                        )
                    """),
                    {
                        "source": content["source"],
                        "source_url": content["url"],  # 使用 URL 作为 source_url
                        "title": content["title"],
                        "summary": content["summary"],
                        "url": content["url"],
                        "tags": content["tags"],
                        "published_at": datetime.now(),
                        "quality_score": 0.8,
                    }
                )
                
                await db.commit()
                inserted_count += 1
                print(f"✅ 已插入: [{content['source']}] {content['title']}")
                
            except Exception as e:
                print(f"❌ 插入失败: {content['title']}, 错误: {e}")
                await db.rollback()
                continue
        
        print("\n" + "=" * 60)
        print(f"✅ 完成！成功插入 {inserted_count} 条内容")
        print("=" * 60)
        
        # 显示当前内容库统计
        result = await db.execute(
            text("""
                SELECT source, COUNT(*) as count
                FROM content_library
                GROUP BY source
                ORDER BY count DESC
            """)
        )
        
        print("\n📊 内容库统计：")
        for row in result.fetchall():
            print(f"  {row[0]}: {row[1]} 条")
    
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
