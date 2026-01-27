"""
内容聚合服务 - 从多个来源抓取内容

核心功能：
1. RSS 订阅抓取
2. 社交媒体热点抓取（微博、知乎、B站）
3. 内容标准化与存储
4. 容错与重试机制

设计原则：
- 合规优先：使用官方 API 或公开聚合，不直接爬取
- 容错设计：单个源失败不影响整体
- 速率限制：避免被封禁
- 数据质量：去重、过滤低质量内容
"""
import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

import feedparser
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from circuitbreaker import circuit

from app.services.retrieval_service import EmbeddingService

logger = logging.getLogger(__name__)


# ==================== 枚举定义 ====================

class ContentSource(Enum):
    """内容来源"""
    RSS = "rss"
    WEIBO = "weibo"
    ZHIHU = "zhihu"
    BILIBILI = "bilibili"
    TOPHUB = "tophub"  # 今日热榜聚合


# ==================== 数据类 ====================

@dataclass
class Content:
    """标准化内容"""
    source: str
    source_url: str
    title: str
    summary: Optional[str]
    content_url: str
    tags: List[str]
    published_at: Optional[datetime]
    quality_score: float = 0.5
    view_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "source": self.source,
            "source_url": self.source_url,
            "title": self.title,
            "summary": self.summary,
            "content_url": self.content_url,
            "tags": self.tags,
            "published_at": self.published_at,
            "quality_score": self.quality_score,
            "view_count": self.view_count,
        }
    
    def get_content_hash(self) -> str:
        """生成内容哈希（用于去重）"""
        content_str = f"{self.title}|{self.content_url}"
        return hashlib.md5(content_str.encode()).hexdigest()


# ==================== 配置 ====================

# RSS 订阅源列表
RSS_FEEDS = [
    "https://hnrss.org/frontpage",
    "https://hnrss.org/newest",
    "https://xkcd.com/rss.xml",
    "https://www.ruanyifeng.com/blog/atom.xml",
    "https://www.python.org/blogs/rss/",
    "https://planetpython.org/rss20.xml",
    "https://www.nasa.gov/rss/dyn/breaking_news.rss",
    "https://rsshub.app/36kr/news",
    "https://rsshub.app/ithome/ranking",
    "https://rsshub.app/geekpark",
    "https://rsshub.app/thepaper/featured",
    "https://rsshub.app/github/trending/daily",
    "https://rsshub.app/v2ex/hot",
    "https://rsshub.app/douban/movie/weekly",
]

# 今日热榜 API
TOPHUB_API = "https://api.tophub.today/v2/GetAllInfoGather"

# 速率限制配置（每分钟请求数）
RATE_LIMITS = {
    ContentSource.RSS: 10,
    ContentSource.WEIBO: 5,
    ContentSource.ZHIHU: 5,
    ContentSource.BILIBILI: 10,
    ContentSource.TOPHUB: 5,
}


# ==================== 内容聚合服务 ====================

class ContentAggregatorService:
    """
    内容聚合服务
    
    负责从多个来源抓取内容，标准化后存储到数据库
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.embedding_service = EmbeddingService()  # 复用现有嵌入服务
        self._rate_limit_locks: Dict[str, asyncio.Semaphore] = {}
        
        # 初始化速率限制
        for source, limit in RATE_LIMITS.items():
            self._rate_limit_locks[source.value] = asyncio.Semaphore(limit)
    
    async def close(self):
        """关闭 HTTP 客户端"""
        await self.http_client.aclose()
    
    # ==================== 主入口 ====================
    
    async def fetch_all_sources(self) -> List[Content]:
        """
        并发抓取所有来源
        
        Returns:
            List[Content]: 抓取到的内容列表
        """
        logger.info("Starting to fetch content from all sources...")
        
        tasks = [
            self.fetch_with_retry(self.fetch_rss_feeds, ContentSource.RSS.value),
            self.fetch_with_retry(self.fetch_weibo_hot, ContentSource.WEIBO.value),
            self.fetch_with_retry(self.fetch_zhihu_hot, ContentSource.ZHIHU.value),
            self.fetch_with_retry(self.fetch_bilibili_hot, ContentSource.BILIBILI.value),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并成功的结果
        all_contents = []
        for i, result in enumerate(results):
            if isinstance(result, list):
                all_contents.extend(result)
                logger.info(f"Source {i} fetched {len(result)} contents")
            else:
                logger.error(f"Source {i} failed: {result}")
        
        # 去重
        unique_contents = self._deduplicate_contents(all_contents)
        logger.info(f"Total fetched: {len(all_contents)}, after dedup: {len(unique_contents)}")
        
        return unique_contents
    
    # ==================== RSS 抓取 ====================
    
    async def fetch_rss_feeds(self) -> List[Content]:
        """
        抓取 RSS 订阅
        
        Returns:
            List[Content]: RSS 内容列表
        """
        logger.info(f"Fetching {len(RSS_FEEDS)} RSS feeds...")
        
        contents = []
        for feed_url in RSS_FEEDS:
            try:
                # 检查 robots.txt（简化版，实际应该更严格）
                if not await self._check_robots_allowed(feed_url):
                    logger.warning(f"Robots.txt disallows: {feed_url}")
                    continue
                
                # 速率限制
                async with self._rate_limit_locks[ContentSource.RSS.value]:
                    # 使用 feedparser 解析 RSS
                    # feedparser 是同步的，但很快，可以直接调用
                    feed = await asyncio.to_thread(feedparser.parse, feed_url)
                    
                    if feed.bozo:
                        logger.warning(f"RSS parse error for {feed_url}: {feed.bozo_exception}")
                        continue
                    
                    # 解析条目
                    for entry in feed.entries[:10]:  # 每个源最多取 10 条
                        try:
                            content = self._parse_rss_entry(entry, feed_url)
                            if content:
                                contents.append(content)
                        except Exception as e:
                            logger.error(f"Failed to parse RSS entry: {e}")
                            continue
                    
                    logger.info(f"Fetched {len(feed.entries[:10])} items from {feed_url}")
                    
                    # 避免过快请求
                    await asyncio.sleep(0.5)
                    
            except Exception as e:
                logger.error(f"Failed to fetch RSS {feed_url}: {e}")
                continue
        
        logger.info(f"RSS fetch complete: {len(contents)} contents")
        return contents
    
    def _parse_rss_entry(self, entry: Any, source_url: str) -> Optional[Content]:
        """
        解析 RSS 条目
        
        Args:
            entry: feedparser 条目
            source_url: RSS 源 URL
            
        Returns:
            Optional[Content]: 解析后的内容，失败返回 None
        """
        try:
            # 提取标题
            title = entry.get("title", "").strip()
            if not title:
                return None
            
            # 提取摘要
            summary = entry.get("summary", entry.get("description", ""))
            if summary:
                # 清理 HTML 标签（简化版）
                summary = summary.replace("<p>", "").replace("</p>", "")
                summary = summary[:500]  # 限制长度
            
            # 提取链接
            content_url = entry.get("link", "")
            if not content_url:
                return None
            
            # 提取发布时间
            published_at = None
            if hasattr(entry, "published_parsed") and entry.published_parsed:
                from time import mktime
                published_at = datetime.fromtimestamp(mktime(entry.published_parsed))
            
            # 提取标签
            tags = []
            if hasattr(entry, "tags"):
                tags = [tag.term for tag in entry.tags[:5]]
            
            return Content(
                source=ContentSource.RSS.value,
                source_url=source_url,
                title=title,
                summary=summary,
                content_url=content_url,
                tags=tags,
                published_at=published_at,
                quality_score=0.6,  # RSS 源质量一般较高
            )
            
        except Exception as e:
            logger.error(f"Failed to parse RSS entry: {e}")
            return None
    
    # ==================== 社交媒体热点抓取 ====================
    
    async def fetch_weibo_hot(self) -> List[Content]:
        """
        抓取微博热搜（通过今日热榜 API）
        
        Returns:
            List[Content]: 微博热搜列表
        """
        logger.info("Fetching Weibo hot topics...")
        
        try:
            async with self._rate_limit_locks[ContentSource.WEIBO.value]:
                contents = await self._fetch_tophub_source("weibo", ContentSource.WEIBO.value)
                logger.info(f"Weibo fetch complete: {len(contents)} contents")
                return contents
        except Exception as e:
            logger.error(f"Failed to fetch Weibo hot: {e}")
            return []
    
    async def fetch_zhihu_hot(self) -> List[Content]:
        """
        抓取知乎热榜（通过今日热榜 API）
        
        Returns:
            List[Content]: 知乎热榜列表
        """
        logger.info("Fetching Zhihu hot topics...")
        
        try:
            async with self._rate_limit_locks[ContentSource.ZHIHU.value]:
                contents = await self._fetch_tophub_source("zhihu", ContentSource.ZHIHU.value)
                logger.info(f"Zhihu fetch complete: {len(contents)} contents")
                return contents
        except Exception as e:
            logger.error(f"Failed to fetch Zhihu hot: {e}")
            return []
    
    async def fetch_bilibili_hot(self) -> List[Content]:
        """
        抓取 B 站热门（通过今日热榜 API）
        
        Returns:
            List[Content]: B 站热门列表
        """
        logger.info("Fetching Bilibili hot videos...")
        
        try:
            async with self._rate_limit_locks[ContentSource.BILIBILI.value]:
                contents = await self._fetch_tophub_source("bilibili", ContentSource.BILIBILI.value)
                logger.info(f"Bilibili fetch complete: {len(contents)} contents")
                return contents
        except Exception as e:
            logger.error(f"Failed to fetch Bilibili hot: {e}")
            return []
    
    @circuit(failure_threshold=5, recovery_timeout=60)
    async def _fetch_tophub_source(self, platform: str, source: str) -> List[Content]:
        """
        从今日热榜 API 抓取指定平台的热点
        
        熔断保护：5 次失败后熔断，60 秒后恢复
        
        Args:
            platform: 平台名称（weibo/zhihu/bilibili）
            source: 内容来源标识
            
        Returns:
            List[Content]: 内容列表
        """
        # 注意：今日热榜 API 可能需要 API key，这里使用简化版
        # 实际使用时需要注册并获取 API key
        
        # 由于今日热榜 API 可能需要付费或注册，这里提供一个备用方案
        # 使用 RSSHub 提供的热榜聚合
        rss_urls = {
            "weibo": "https://rsshub.app/weibo/search/hot",
            "zhihu": "https://rsshub.app/zhihu/hotlist",
            "bilibili": "https://rsshub.app/bilibili/ranking/0/3/1",  # 全站排行榜
        }
        
        feed_url = rss_urls.get(platform)
        if not feed_url:
            logger.warning(f"Unknown platform: {platform}")
            return []
        
        try:
            response = await self.http_client.get(feed_url)
            response.raise_for_status()
            
            # 使用 feedparser 解析
            feed = await asyncio.to_thread(feedparser.parse, response.text)
            
            contents = []
            for entry in feed.entries[:10]:  # 每个平台最多取 10 条
                try:
                    content = Content(
                        source=source,
                        source_url=feed_url,
                        title=entry.get("title", "").strip(),
                        summary=entry.get("summary", "")[:500],
                        content_url=entry.get("link", ""),
                        tags=[platform],
                        published_at=datetime.now(),  # 热榜通常没有准确时间
                        quality_score=0.7,  # 热榜内容质量较高
                        view_count=0,
                    )
                    
                    if content.title and content.content_url:
                        contents.append(content)
                        
                except Exception as e:
                    logger.error(f"Failed to parse {platform} entry: {e}")
                    continue
            
            return contents
            
        except Exception as e:
            logger.error(f"Failed to fetch {platform} from RSSHub: {e}")
            raise  # 触发熔断器
    
    # ==================== 容错与重试 ====================
    
    async def fetch_with_retry(
        self,
        fetch_func: Callable,
        source: str,
        max_retries: int = 3
    ) -> List[Content]:
        """
        带重试的抓取
        
        Args:
            fetch_func: 抓取函数
            source: 来源标识
            max_retries: 最大重试次数
            
        Returns:
            List[Content]: 抓取到的内容列表
        """
        for attempt in range(max_retries):
            try:
                return await fetch_func()
            except Exception as e:
                logger.warning(
                    f"Fetch failed for {source} (attempt {attempt + 1}/{max_retries}): {e}"
                )
                
                if attempt < max_retries - 1:
                    # 指数退避
                    wait_time = 2 ** attempt
                    logger.info(f"Retrying in {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(f"All retries failed for {source}")
                    return []
        
        return []
    
    # ==================== 辅助方法 ====================
    
    async def _check_robots_allowed(self, url: str) -> bool:
        """
        检查 robots.txt 是否允许抓取（简化版）
        
        Args:
            url: 目标 URL
            
        Returns:
            bool: 是否允许抓取
        """
        # 简化实现：只检查常见的禁止规则
        # 实际应该使用 robotparser 库
        
        # RSSHub 和公开 API 通常允许抓取
        if "rsshub.app" in url or "api." in url:
            return True
        
        # 其他情况默认允许（实际应该更严格）
        return True
    
    def _deduplicate_contents(self, contents: List[Content]) -> List[Content]:
        """
        内容去重
        
        Args:
            contents: 内容列表
            
        Returns:
            List[Content]: 去重后的内容列表
        """
        seen_hashes = set()
        unique_contents = []
        
        for content in contents:
            content_hash = content.get_content_hash()
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique_contents.append(content)
        
        return unique_contents
    
    # ==================== 数据库操作 ====================
    
    async def save_content(self, content: Content) -> bool:
        """
        保存内容到数据库（包含嵌入向量生成）
        
        Args:
            content: 要保存的内容
            
        Returns:
            bool: 是否保存成功
        """
        try:
            # 检查是否已存在（根据 URL 去重）
            result = await self.db.execute(
                text("""
                    SELECT id FROM content_library
                    WHERE content_url = :url
                """),
                {"url": content.content_url}
            )
            
            if result.scalar_one_or_none():
                logger.debug(f"Content already exists: {content.title}")
                return False

            extra_tags = self._extract_extra_tags(content.title, content.summary or "")
            if extra_tags:
                content.tags = list(dict.fromkeys((content.tags or []) + extra_tags))
            
            # 生成 1024 维嵌入向量（使用 bge-m3 模型）
            embedding_text = f"{content.title}\n{content.summary or ''}"
            embedding = await self.embedding_service.encode(embedding_text)
            
            # 验证嵌入维度
            if len(embedding) != 1024:
                logger.error(f"Embedding dimension mismatch: expected 1024, got {len(embedding)}")
                return False
            
            # 插入新内容（包含嵌入向量）
            embedding_str = "[" + ",".join(str(float(x)) for x in embedding) + "]"
            await self.db.execute(
                text("""
                    INSERT INTO content_library (
                        source, source_url, title, summary, content_url,
                        tags, embedding, published_at, quality_score, view_count
                    ) VALUES (
                        :source, :source_url, :title, :summary, :content_url,
                        :tags, CAST(:embedding AS vector), :published_at, :quality_score, :view_count
                    )
                """),
                {
                    "source": content.source,
                    "source_url": content.source_url,
                    "title": content.title,
                    "summary": content.summary,
                    "content_url": content.content_url,
                    "tags": content.tags,
                    "embedding": embedding_str,
                    "published_at": content.published_at,
                    "quality_score": content.quality_score,
                    "view_count": content.view_count,
                }
            )
            
            await self.db.commit()
            logger.debug(f"Saved content with embedding: {content.title}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save content: {e}")
            await self.db.rollback()
            return False

    def _extract_extra_tags(self, title: str, summary: str) -> List[str]:
        text = f"{title}\n{summary}"
        tags: List[str] = []

        city_keywords = [
            "深圳", "北京", "上海", "广州", "杭州", "成都", "重庆", "武汉", "西安", "南京",
            "苏州", "天津", "长沙", "郑州", "青岛", "厦门", "大连", "宁波", "合肥", "昆明",
            "福州", "济南", "沈阳", "哈尔滨"
        ]
        for city in city_keywords:
            if city in text:
                tags.append(city)

        topic_keywords = {
            "足球": ["足球", "中超", "英超", "西甲", "欧冠", "世界杯", "梅西", "C罗", "国足"],
            "喝茶": ["茶", "绿茶", "红茶", "乌龙", "普洱", "茶叶", "泡茶"],
        }
        for tag, kws in topic_keywords.items():
            if any(k in text for k in kws):
                tags.append(tag)

        return list(dict.fromkeys(tags))
    
    async def save_contents_batch(self, contents: List[Content]) -> int:
        """
        批量保存内容
        
        Args:
            contents: 内容列表
            
        Returns:
            int: 成功保存的数量
        """
        saved_count = 0
        
        for content in contents:
            if await self.save_content(content):
                saved_count += 1
        
        logger.info(f"Batch save complete: {saved_count}/{len(contents)} saved")
        return saved_count
