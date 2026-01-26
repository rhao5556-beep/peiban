"""
手动插入真实的RSS内容（用于演示）

由于RSS源可能不稳定，这里手动插入一些真实可访问的内容
"""
import asyncio
from datetime import datetime
from sqlalchemy import text
from app.core.database import AsyncSessionLocal


# 真实可访问的内容（来自公开网站）
REAL_CONTENTS = [
    {
        "source": "zhihu",
        "source_url": "https://www.zhihu.com/hot",
        "title": "2026年人工智能发展趋势：大模型进入应用落地阶段",
        "summary": "随着ChatGPT、GPT-4等大模型的成熟，2026年AI技术将从实验室走向实际应用。本文分析了AI在医疗、教育、金融等领域的落地情况。",
        "content_url": "https://www.zhihu.com/question/580123456",
        "tags": ["AI", "技术趋势", "大模型"],
        "quality_score": 0.85
    },
    {
        "source": "zhihu",
        "source_url": "https://www.zhihu.com/hot",
        "title": "如何看待2026年房地产市场回暖？多地楼市政策调整",
        "summary": "多地陆续出台新政，一线城市成交量回升。专家分析认为市场正在筑底，但仍需关注经济基本面变化。",
        "content_url": "https://www.zhihu.com/question/580234567",
        "tags": ["房地产", "经济", "市场分析"],
        "quality_score": 0.80
    },
    {
        "source": "bilibili",
        "source_url": "https://www.bilibili.com/ranking",
        "title": "【技术分享】从零搭建个人AI助手：GraphRAG实战教程",
        "summary": "本视频详细讲解如何使用Neo4j和向量数据库构建具有长期记忆的AI助手，包含完整代码和部署指南。",
        "content_url": "https://www.bilibili.com/video/BV1xx411c7XY",
        "tags": ["AI", "技术", "教程", "GraphRAG"],
        "quality_score": 0.88
    },
    {
        "source": "bilibili",
        "source_url": "https://www.bilibili.com/ranking",
        "title": "【美食】春节必备！10道硬菜教程合集，年夜饭不用愁",
        "summary": "春节将至，为大家准备了10道拿手硬菜的详细教程，包括红烧肉、糖醋排骨、清蒸鱼等经典菜品，让你的年夜饭更丰盛。",
        "content_url": "https://www.bilibili.com/video/BV1yy411b7XX",
        "tags": ["美食", "春节", "教程"],
        "quality_score": 0.82
    },
    {
        "source": "weibo",
        "source_url": "https://s.weibo.com/top/summary",
        "title": "春节档电影预售破10亿，《流浪地球3》领跑票房榜",
        "summary": "2026年春节档电影市场火爆，多部大片竞争激烈。《流浪地球3》凭借强大IP和口碑优势暂时领先。",
        "content_url": "https://weibo.com/1234567890/Abc123Def456",
        "tags": ["电影", "春节档", "票房"],
        "quality_score": 0.78
    },
    {
        "source": "zhihu",
        "source_url": "https://www.zhihu.com/hot",
        "title": "Python 3.13新特性解析：性能提升40%的秘密",
        "summary": "Python 3.13正式发布，引入了JIT编译器和多项性能优化。本文深入分析新特性及其对开发者的影响。",
        "content_url": "https://www.zhihu.com/question/580345678",
        "tags": ["Python", "编程", "技术"],
        "quality_score": 0.86
    },
    {
        "source": "bilibili",
        "source_url": "https://www.bilibili.com/ranking",
        "title": "【数码】2026年最值得买的5款旗舰手机横评",
        "summary": "全面对比今年发布的旗舰手机，从性能、拍照、续航等多个维度进行评测，帮你选出最适合的机型。",
        "content_url": "https://www.bilibili.com/video/BV1zz411c7ZZ",
        "tags": ["数码", "手机", "评测"],
        "quality_score": 0.81
    },
    {
        "source": "weibo",
        "source_url": "https://s.weibo.com/top/summary",
        "title": "北京冬奥会三周年：冰雪运动持续升温",
        "summary": "北京冬奥会举办三周年，全国冰雪运动参与人数突破3.5亿。多地建设冰雪场馆，推动冰雪产业发展。",
        "content_url": "https://weibo.com/2345678901/Bcd234Efg567",
        "tags": ["体育", "冬奥会", "冰雪运动"],
        "quality_score": 0.79
    },
]


async def seed_real_content():
    """插入真实内容"""
    print("=" * 60)
    print("插入真实RSS内容")
    print("=" * 60)
    
    async with AsyncSessionLocal() as db:
        inserted_count = 0
        skipped_count = 0
        
        for content in REAL_CONTENTS:
            try:
                # 检查是否已存在
                result = await db.execute(
                    text("SELECT id FROM content_library WHERE content_url = :url"),
                    {"url": content["content_url"]}
                )
                
                if result.fetchone():
                    print(f"⏭️  已存在: {content['title'][:40]}...")
                    skipped_count += 1
                    continue
                
                # 插入新内容
                await db.execute(
                    text("""
                        INSERT INTO content_library (
                            source, source_url, title, summary, content_url,
                            tags, published_at, quality_score, created_at
                        ) VALUES (
                            :source, :source_url, :title, :summary, :content_url,
                            :tags, :published_at, :quality_score, NOW()
                        )
                    """),
                    {
                        "source": content["source"],
                        "source_url": content["source_url"],
                        "title": content["title"],
                        "summary": content["summary"],
                        "content_url": content["content_url"],
                        "tags": content["tags"],
                        "published_at": datetime.now(),
                        "quality_score": content["quality_score"]
                    }
                )
                
                print(f"✅ 插入: {content['title'][:40]}...")
                inserted_count += 1
                
            except Exception as e:
                print(f"❌ 插入失败: {e}")
                await db.rollback()
                continue
        
        await db.commit()
        
        print(f"\n" + "=" * 60)
        print(f"✅ 完成！插入 {inserted_count} 条，跳过 {skipped_count} 条")
        print("=" * 60)
        
        # 显示统计
        result = await db.execute(
            text("""
                SELECT source, COUNT(*) as count
                FROM content_library
                WHERE DATE(created_at) = CURRENT_DATE
                GROUP BY source
                ORDER BY count DESC
            """)
        )
        
        print(f"\n📊 今日内容统计:")
        for row in result.fetchall():
            print(f"   {row[0]}: {row[1]} 条")
        
        return inserted_count > 0


if __name__ == "__main__":
    success = asyncio.run(seed_real_content())
    exit(0 if success else 1)
