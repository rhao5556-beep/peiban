"""
简单RSS测试 - 使用公开可用的RSS源
"""
import asyncio
import feedparser
from datetime import datetime
from sqlalchemy import text
from app.core.database import AsyncSessionLocal


# 使用稳定的公开RSS源
PUBLIC_RSS_FEEDS = [
    {
        "url": "https://www.zhihu.com/rss",
        "source": "zhihu",
        "name": "知乎",
        "tags": ["知乎", "问答"]
    },
    {
        "url": "http://www.people.com.cn/rss/it.xml",
        "source": "people",
        "name": "人民网IT",
        "tags": ["科技", "新闻"]
    },
]


async def test_simple_rss():
    """测试简单RSS抓取"""
    print("=" * 60)
    print("简单RSS抓取测试")
    print("=" * 60)
    
    all_contents = []
    
    for feed_config in PUBLIC_RSS_FEEDS:
        print(f"\n📡 抓取: {feed_config['name']} ({feed_config['url']})")
        
        try:
            # 解析RSS
            feed = feedparser.parse(feed_config['url'])
            
            if feed.bozo:
                print(f"⚠️  RSS解析警告: {feed.bozo_exception}")
            
            print(f"✅ 获取到 {len(feed.entries)} 条内容")
            
            # 显示前3条
            for i, entry in enumerate(feed.entries[:3], 1):
                title = entry.get('title', '无标题')
                link = entry.get('link', '')
                print(f"  {i}. {title}")
                print(f"     {link}")
                
                # 准备保存的数据
                all_contents.append({
                    "source": feed_config['source'],
                    "title": title,
                    "summary": entry.get('summary', '')[:200],
                    "url": link,
                    "tags": feed_config['tags'],
                    "published_at": datetime.now()
                })
        
        except Exception as e:
            print(f"❌ 抓取失败: {e}")
            continue
    
    if not all_contents:
        print("\n❌ 未抓取到任何内容")
        return False
    
    # 保存到数据库
    print(f"\n💾 保存 {len(all_contents)} 条内容到数据库...")
    
    async with AsyncSessionLocal() as db:
        saved_count = 0
        
        for content in all_contents:
            try:
                # 检查是否已存在
                result = await db.execute(
                    text("SELECT id FROM content_library WHERE content_url = :url"),
                    {"url": content['url']}
                )
                
                if result.fetchone():
                    print(f"  ⏭️  已存在: {content['title'][:30]}...")
                    continue
                
                # 插入新内容
                await db.execute(
                    text("""
                        INSERT INTO content_library (
                            source, title, summary, content_url, tags,
                            published_at, quality_score, created_at
                        ) VALUES (
                            :source, :title, :summary, :url, :tags,
                            :published_at, 0.7, NOW()
                        )
                    """),
                    {
                        "source": content['source'],
                        "title": content['title'],
                        "summary": content['summary'],
                        "url": content['url'],
                        "tags": content['tags'],
                        "published_at": content['published_at']
                    }
                )
                
                saved_count += 1
                print(f"  ✅ 保存: {content['title'][:30]}...")
                
            except Exception as e:
                print(f"  ❌ 保存失败: {e}")
                continue
        
        await db.commit()
        
        print(f"\n✅ 成功保存 {saved_count}/{len(all_contents)} 条内容")
        
        # 验证数据库
        result = await db.execute(
            text("""
                SELECT COUNT(*) as total, source
                FROM content_library
                WHERE DATE(created_at) = CURRENT_DATE
                GROUP BY source
            """)
        )
        
        print(f"\n📊 今日内容统计:")
        for row in result.fetchall():
            print(f"   {row[1]}: {row[0]} 条")
        
        return saved_count > 0


if __name__ == "__main__":
    success = asyncio.run(test_simple_rss())
    exit(0 if success else 1)
