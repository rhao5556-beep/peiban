"""
RSS内容聚合服务

功能：
1. 从配置的RSS源抓取内容
2. 解析和清洗数据
3. 存储到content_library表
4. 支持多个来源（知乎、B站、微博等）
"""
import logging
import hashlib
from datetime import datetime
from typing import List, Dict, Optional
import feedparser
import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class RSSAggregatorService:
    """RSS内容聚合服务"""
    
    # RSS订阅源配置
    RSS_FEEDS = {
        "zhihu": [
            {
                "url": "https://www.zhihu.com/rss",
                "name": "知乎热榜",
                "tags": ["知乎", "热榜"]
            }
        ],
        "bilibili": [
            {
                "url": "https://rsshub.app/bilibili/ranking/0/3/1",  # 全站排行榜
                "name": "B站热门",
                "tags": ["bilibili", "视频", "热门"]
            }
        ],
        "weibo": [
            {
                "url": "https://rsshub.app/weibo/search/hot",  # 微博热搜
                "name": "微博热搜",
                "tags": ["微博", "热搜"]
            }
        ]
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
    
    @staticmethod
    def _generate_content_id(url: str) -> str:
        """根据URL生成唯一ID"""
        return hashlib.md5(url.encode()).hexdigest()[:16]
    
    @staticmethod
    def _clean_html(text: str) -> str:
        """清理HTML标签"""
        if not text:
            return ""
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', text)
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text)
        return text.strip()
    
    @staticmethod
    def _extract_summary(content: str, max_length: int = 200) -> str:
        """提取摘要"""
        if not content:
            return ""
        content = RSSAggregatorService._clean_html(content)
        if len(content) <= max_length:
            return content
        return content[:max_length] + "..."
    
    @staticmethod
    def _calculate_quality_score(entry: Dict) -> float:
        """计算内容质量分"""
        score = 0.5  # 基础分
        
        # 有摘要加分
        if entry.get("summary"):
            score += 0.1
        
        # 有作者加分
        if entry.get("author"):
            score += 0.1
        
        # 标题长度合理加分
        title = entry.get("title", "")
        if 10 <= len(title) <= 100:
            score += 0.1
        
        # 发布时间越新分数越高
        published = entry.get("published_parsed")
        if published:
            days_old = (datetime.now() - datetime(*published[:6])).days
            if days_old == 0:
                score += 0.2
            elif days_old <= 1:
                score += 0.1
        
        return min(score, 1.0)
    
    async def fetch_feed(self, feed_url: str, source: str, tags: List[str]) -> List[Dict]:
        """
        抓取单个RSS源
        
        Args:
            feed_url: RSS源URL
            source: 来源标识（zhihu/bilibili/weibo）
            tags: 标签列表
            
        Returns:
            解析后的内容列表
        """
        try:
            logger.info(f"Fetching RSS feed: {feed_url}")
            
            # 解析RSS
            feed = feedparser.parse(feed_url)
            
            if feed.bozo:
                logger.warning(f"RSS feed has errors: {feed_url}, error: {feed.bozo_exception}")
            
            contents = []
            
            for entry in feed.entries[:10]:  # 只取前10条
                try:
                    # 提取基本信息
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    
                    if not title or not link:
                        continue
                    
                    # 提取摘要
                    summary = self._extract_summary(
                        entry.get("summary", "") or entry.get("description", "")
                    )
                    
                    # 提取发布时间
                    published_parsed = entry.get("published_parsed")
                    if published_parsed:
                        published_at = datetime(*published_parsed[:6])
                    else:
                        published_at = datetime.now()
                    
                    # 计算质量分
                    quality_score = self._calculate_quality_score(entry)
                    
                    # 组合标签
                    entry_tags = tags.copy()
                    if entry.get("tags"):
                        entry_tags.extend([tag.term for tag in entry.tags[:3]])
                    
                    contents.append({
                        "title": title,
                        "url": link,
                        "summary": summary,
                        "source": source,
                        "tags": entry_tags,
                        "published_at": published_at,
                        "quality_score": quality_score,
                        "author": entry.get("author", "")
                    })
                    
                except Exception as e:
                    logger.warning(f"Failed to parse entry: {e}")
                    continue
            
            logger.info(f"Fetched {len(contents)} items from {feed_url}")
            return contents
            
        except Exception as e:
            logger.error(f"Failed to fetch RSS feed {feed_url}: {e}")
            return []
    
    async def save_content(self, content: Dict) -> bool:
        """
        保存内容到数据库
        
        Args:
            content: 内容字典
            
        Returns:
            是否保存成功
        """
        try:
            # 检查是否已存在（根据URL去重）
            result = await self.db.execute(
                text("""
                    SELECT id FROM content_library
                    WHERE content_url = :url
                """),
                {"url": content["url"]}
            )
            
            if result.fetchone():
                logger.debug(f"Content already exists: {content['url']}")
                return False
            
            # 插入新内容
            await self.db.execute(
                text("""
                    INSERT INTO content_library (
                        source, title, summary, content_url, tags,
                        published_at, quality_score, author, created_at
                    ) VALUES (
                        :source, :title, :summary, :url, :tags,
                        :published_at, :quality_score, :author, NOW()
                    )
                """),
                {
                    "source": content["source"],
                    "title": content["title"],
                    "summary": content["summary"],
                    "url": content["url"],
                    "tags": content["tags"],
                    "published_at": content["published_at"],
                    "quality_score": content["quality_score"],
                    "author": content.get("author", "")
                }
            )
            
            await self.db.commit()
            logger.info(f"Saved content: {content['title']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save content: {e}")
            await self.db.rollback()
            return False
    
    async def aggregate_from_source(self, source: str) -> int:
        """
        从指定来源聚合内容
        
        Args:
            source: 来源标识（zhihu/bilibili/weibo）
            
        Returns:
            成功保存的内容数量
        """
        if source not in self.RSS_FEEDS:
            logger.error(f"Unknown source: {source}")
            return 0
        
        feeds = self.RSS_FEEDS[source]
        total_saved = 0
        
        for feed_config in feeds:
            contents = await self.fetch_feed(
                feed_config["url"],
                source,
                feed_config["tags"]
            )
            
            for content in contents:
                if await self.save_content(content):
                    total_saved += 1
        
        logger.info(f"Aggregated {total_saved} new items from {source}")
        return total_saved
    
    async def aggregate_all(self) -> Dict[str, int]:
        """
        从所有来源聚合内容
        
        Returns:
            各来源保存的内容数量
        """
        results = {}
        
        for source in self.RSS_FEEDS.keys():
            count = await self.aggregate_from_source(source)
            results[source] = count
        
        total = sum(results.values())
        logger.info(f"Total aggregated: {total} items from {len(results)} sources")
        
        return results
    
    async def cleanup_old_content(self, days: int = 30) -> int:
        """
        清理旧内容
        
        Args:
            days: 保留天数
            
        Returns:
            归档的内容数量
        """
        try:
            result = await self.db.execute(
                text("""
                    UPDATE content_library
                    SET is_active = FALSE
                    WHERE published_at < NOW() - (:days || ' days')::interval
                      AND is_active = TRUE
                    RETURNING id
                """),
                {"days": days}
            )
            
            deleted_count = len(result.fetchall())
            await self.db.commit()
            
            logger.info(f"Archived {deleted_count} old contents (older than {days} days)")
            return deleted_count
            
        except Exception as e:
            logger.error(f"Failed to cleanup old content: {e}")
            await self.db.rollback()
            return 0
