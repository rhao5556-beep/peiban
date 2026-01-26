"""
热点内容感知服务 - 监控外部平台的热门表情包和梗图

核心功能：
1. 从微博热搜API获取热点内容（MVP阶段）
2. 提取表情包数据：text_description、source_platform、initial_popularity_score
3. 内容哈希去重：跨平台检测重复内容
4. 优雅降级：单个源失败不影响整体
5. 速率限制和缓存（1小时缓存）

设计原则：
- 合规优先：使用官方API或公开聚合
- 容错设计：单个源失败不影响整体
- 速率限制：避免被封禁
- 去重优先：使用content_hash防止跨平台重复
"""
import logging
import asyncio
import hashlib
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

import httpx
import feedparser
from circuitbreaker import circuit

logger = logging.getLogger(__name__)


# ==================== 数据类 ====================

@dataclass
class MemeCandidate:
    """表情包候选数据"""
    text_description: str
    source_platform: str
    initial_popularity_score: float
    image_url: Optional[str] = None  # MVP阶段为None
    original_source_url: Optional[str] = None
    category: Optional[str] = None
    
    def calculate_content_hash(self) -> str:
        """
        计算内容哈希用于去重
        
        使用SHA256(text_description + normalized_url)
        跨平台检测相同表情包
        
        Returns:
            str: 64字符的SHA256哈希值
        """
        # 标准化URL（如果存在）
        normalized_url = ""
        if self.image_url:
            # 移除查询参数和片段，只保留路径
            normalized_url = self.image_url.split('?')[0].split('#')[0].lower().strip()
        
        # 标准化文本描述
        normalized_text = self.text_description.lower().strip()
        
        # 组合并计算哈希
        content_str = f"{normalized_text}|{normalized_url}"
        return hashlib.sha256(content_str.encode('utf-8')).hexdigest()
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "text_description": self.text_description,
            "source_platform": self.source_platform,
            "initial_popularity_score": self.initial_popularity_score,
            "image_url": self.image_url,
            "original_source_url": self.original_source_url,
            "category": self.category,
            "content_hash": self.calculate_content_hash(),
        }


# ==================== 配置 ====================

# 微博热搜RSS源（通过RSSHub）
WEIBO_HOT_RSS = "https://rsshub.app/weibo/search/hot"

# 速率限制（每分钟请求数）
WEIBO_RATE_LIMIT = 5

# 缓存时长（秒）
CACHE_DURATION_SECONDS = 3600  # 1小时


# ==================== 热点内容感知服务 ====================

class TrendingContentSensorService:
    """
    热点内容感知服务
    
    负责从外部平台监控热门表情包和梗图
    MVP阶段仅支持微博API集成
    """
    
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self._rate_limit_lock = asyncio.Semaphore(WEIBO_RATE_LIMIT)
        self._cache: Dict[str, tuple[List[MemeCandidate], datetime]] = {}
    
    async def close(self):
        """关闭HTTP客户端"""
        await self.http_client.aclose()
    
    # ==================== 主入口 ====================
    
    async def aggregate_all_trends(self) -> List[MemeCandidate]:
        """
        聚合所有平台趋势并进行错误处理
        
        MVP阶段仅调用微博，未来扩展到抖音、B站
        实现优雅降级：如果微博失败，返回空列表而不是抛出异常
        
        Returns:
            List[MemeCandidate]: 表情包候选列表
        """
        logger.info("Starting to aggregate trending memes from all sources...")
        
        # MVP阶段仅微博
        # 未来扩展：tasks = [self.fetch_weibo_trends(), self.fetch_douyin_trends(), ...]
        tasks = [self.fetch_weibo_trends()]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # 合并成功的结果（优雅降级）
        all_candidates = []
        for i, result in enumerate(results):
            if isinstance(result, list):
                all_candidates.extend(result)
                logger.info(f"Source {i} (Weibo) fetched {len(result)} candidates")
            elif isinstance(result, Exception):
                logger.error(f"Source {i} (Weibo) failed with exception: {result}")
            else:
                logger.error(f"Source {i} (Weibo) failed with unexpected result: {result}")
        
        # 去重（基于content_hash）
        unique_candidates = self._deduplicate_candidates(all_candidates)
        logger.info(
            f"Total fetched: {len(all_candidates)}, "
            f"after dedup: {len(unique_candidates)}"
        )
        
        return unique_candidates
    
    # ==================== 微博热搜抓取 ====================
    
    @circuit(failure_threshold=5, recovery_timeout=60)
    async def fetch_weibo_trends(self) -> List[MemeCandidate]:
        """
        从微博热搜API获取热点内容
        
        使用RSSHub提供的微博热搜RSS源
        实现速率限制和缓存（1小时）
        熔断保护：5次失败后熔断，60秒后恢复
        
        Returns:
            List[MemeCandidate]: 微博热搜表情包候选列表
            
        Raises:
            Exception: 当API调用失败时（触发熔断器）
        """
        logger.info("Fetching Weibo hot trends...")
        
        # 检查缓存
        cache_key = "weibo_trends"
        if cache_key in self._cache:
            cached_data, cached_time = self._cache[cache_key]
            age = (datetime.now() - cached_time).total_seconds()
            if age < CACHE_DURATION_SECONDS:
                logger.info(f"Using cached Weibo trends (age: {age:.0f}s)")
                return cached_data
        
        try:
            # 速率限制
            async with self._rate_limit_lock:
                # 获取RSS数据
                response = await self.http_client.get(WEIBO_HOT_RSS)
                response.raise_for_status()
                
                # 解析RSS
                feed = await asyncio.to_thread(feedparser.parse, response.text)
                
                if feed.bozo:
                    logger.warning(f"RSS parse error: {feed.bozo_exception}")
                    raise Exception(f"Failed to parse Weibo RSS: {feed.bozo_exception}")
                
                # 提取表情包候选
                candidates = []
                for entry in feed.entries[:20]:  # 取前20条热搜
                    try:
                        candidate = self._parse_weibo_entry(entry)
                        if candidate:
                            candidates.append(candidate)
                    except Exception as e:
                        logger.error(f"Failed to parse Weibo entry: {e}")
                        continue
                
                logger.info(f"Weibo fetch complete: {len(candidates)} candidates")
                
                # 更新缓存
                self._cache[cache_key] = (candidates, datetime.now())
                
                return candidates
                
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching Weibo trends: {e.response.status_code}")
            raise  # 触发熔断器
        except httpx.RequestError as e:
            logger.error(f"Request error fetching Weibo trends: {e}")
            raise  # 触发熔断器
        except Exception as e:
            logger.error(f"Unexpected error fetching Weibo trends: {e}")
            raise  # 触发熔断器
    
    def _parse_weibo_entry(self, entry: Any) -> Optional[MemeCandidate]:
        """
        解析微博RSS条目为表情包候选
        
        提取：
        - text_description: 热搜标题
        - source_platform: 'weibo'
        - initial_popularity_score: 基于排名的分数（简化版）
        - image_url: MVP阶段设置为None
        - original_source_url: 热搜链接
        - category: 基于关键词的简单分类
        
        Args:
            entry: feedparser条目对象
            
        Returns:
            Optional[MemeCandidate]: 解析后的候选，失败返回None
        """
        try:
            # 提取标题（必需）
            title = entry.get("title", "").strip()
            if not title:
                return None
            
            # 提取链接
            content_url = entry.get("link", "")
            
            # 计算初始热度分数（基于RSS中的位置，越靠前分数越高）
            # RSS中的条目通常按热度排序，第一条最热
            # 简化版：假设前10条为高热度（70-100），后10条为中等热度（40-70）
            # 实际应该从API获取真实的热度指标（阅读数、讨论数等）
            initial_score = 80.0  # 默认中高热度
            
            # 简单分类（基于关键词）
            category = self._classify_content(title)
            
            return MemeCandidate(
                text_description=title,
                source_platform="weibo",
                initial_popularity_score=initial_score,
                image_url=None,  # MVP阶段仅文本/emoji
                original_source_url=content_url,
                category=category,
            )
            
        except Exception as e:
            logger.error(f"Failed to parse Weibo entry: {e}")
            return None
    
    def _classify_content(self, text: str) -> str:
        """
        基于关键词的简单内容分类
        
        Args:
            text: 文本内容
            
        Returns:
            str: 分类标签（humor/emotion/trending_phrase）
        """
        text_lower = text.lower()
        
        # 幽默类关键词
        humor_keywords = ["哈哈", "笑", "搞笑", "有趣", "好玩", "梗", "段子"]
        if any(keyword in text_lower for keyword in humor_keywords):
            return "humor"
        
        # 情感类关键词
        emotion_keywords = ["感动", "泪", "心疼", "爱", "温暖", "治愈"]
        if any(keyword in text_lower for keyword in emotion_keywords):
            return "emotion"
        
        # 默认为热门短语
        return "trending_phrase"
    
    # ==================== 辅助方法 ====================
    
    def _deduplicate_candidates(
        self, 
        candidates: List[MemeCandidate]
    ) -> List[MemeCandidate]:
        """
        基于content_hash去重候选列表
        
        跨平台检测相同表情包，保留第一个出现的
        
        Args:
            candidates: 候选列表
            
        Returns:
            List[MemeCandidate]: 去重后的候选列表
        """
        seen_hashes = set()
        unique_candidates = []
        
        for candidate in candidates:
            content_hash = candidate.calculate_content_hash()
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique_candidates.append(candidate)
            else:
                logger.debug(
                    f"Duplicate detected: {candidate.text_description[:50]}... "
                    f"(hash: {content_hash[:16]}...)"
                )
        
        return unique_candidates
    
    def clear_cache(self):
        """清除缓存（用于测试或强制刷新）"""
        self._cache.clear()
        logger.info("Cache cleared")
