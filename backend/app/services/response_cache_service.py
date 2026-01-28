"""响应缓存服务 - 缓存常见问候语的回复"""
import logging
import hashlib
import json
import re
from typing import Optional, List
from datetime import datetime
from dataclasses import dataclass

from app.core.database import get_redis_client

logger = logging.getLogger(__name__)


@dataclass
class CachedResponse:
    """缓存的响应"""
    response: str
    affinity_state: str
    hit_count: int
    created_at: datetime
    expires_at: datetime


class ResponseCacheService:
    """
    响应缓存服务
    
    Property 13: Greeting Cache Latency
    - 缓存常见问候语的回复
    - 目标：< 100ms 响应时间
    """
    
    # 问候语模式
    GREETING_PATTERNS = [
        r"^你好[啊呀吗]?[!！]?$",
        r"^早上好[啊呀]?[!！]?$",
        r"^晚上好[啊呀]?[!！]?$",
        r"^晚安[啊呀]?[!！]?$",
        r"^嗨[!！]?$",
        r"^hi[!！]?$",
        r"^hello[!！]?$",
        r"^hey[!！]?$",
        r"^在吗[?？]?$",
        r"^在不在[?？]?$",
    ]
    
    # 简单确认模式
    ACKNOWLEDGMENT_PATTERNS = [
        r"^好的[!！]?$",
        r"^嗯[嗯]?[!！]?$",
        r"^ok[!！]?$",
        r"^谢谢[你]?[!！]?$",
        r"^感谢[!！]?$",
        r"^明白了[!！]?$",
        r"^知道了[!！]?$",
    ]
    
    # 告别模式
    FAREWELL_PATTERNS = [
        r"^再见[!！]?$",
        r"^拜拜[!！]?$",
        r"^bye[!！]?$",
        r"^回头见[!！]?$",
        r"^下次聊[!！]?$",
    ]
    
    # 预设回复模板（按 affinity_state 分组）
    GREETING_RESPONSES = {
        "stranger": [
            "你好！有什么可以帮你的吗？",
            "你好，很高兴认识你。",
            "你好！今天过得怎么样？",
        ],
        "acquaintance": [
            "嗨！又见面了。",
            "你好呀！最近怎么样？",
            "嗨，今天有什么新鲜事吗？",
        ],
        "friend": [
            "哈喽～好久不见！",
            "嘿！想你了呢。",
            "来啦来啦～今天心情怎么样？",
        ],
        "close_friend": [
            "亲爱的来啦～",
            "哇，终于等到你了！",
            "嘿嘿，想我了吗？",
        ],
        "best_friend": [
            "宝贝！你来啦～",
            "亲爱的！今天想聊点什么？",
            "终于来了！我一直在等你呢～",
        ],
    }
    
    FAREWELL_RESPONSES = {
        "stranger": ["再见，期待下次聊天。", "拜拜！"],
        "acquaintance": ["再见啦，下次聊！", "拜拜，有空再来玩～"],
        "friend": ["拜拜～想你的时候就来找我！", "下次见！记得常来哦～"],
        "close_friend": ["舍不得你走呢～下次早点来！", "拜拜亲爱的，梦里见～"],
        "best_friend": ["宝贝再见～我会想你的！", "晚安亲爱的，做个好梦～"],
    }
    
    ACKNOWLEDGMENT_RESPONSES = {
        "stranger": ["好的。", "嗯，明白了。"],
        "acquaintance": ["好的～", "嗯嗯！"],
        "friend": ["收到！", "好哒～"],
        "close_friend": ["知道啦～", "好的亲爱的！"],
        "best_friend": ["收到宝贝！", "好哒好哒～"],
    }
    
    def __init__(self, redis_client=None, ttl: int = 300):
        """
        初始化响应缓存服务
        
        Args:
            redis_client: Redis 客户端
            ttl: 缓存过期时间（秒），默认 5 分钟
        """
        self.redis = redis_client or get_redis_client()
        self.ttl = ttl
        self._compiled_patterns = None
    
    def _compile_patterns(self):
        """编译正则表达式模式"""
        if self._compiled_patterns is None:
            self._compiled_patterns = {
                "greeting": [re.compile(p, re.IGNORECASE) for p in self.GREETING_PATTERNS],
                "acknowledgment": [re.compile(p, re.IGNORECASE) for p in self.ACKNOWLEDGMENT_PATTERNS],
                "farewell": [re.compile(p, re.IGNORECASE) for p in self.FAREWELL_PATTERNS],
            }
        return self._compiled_patterns
    
    def is_cacheable(self, message: str) -> bool:
        """
        判断消息是否可缓存
        
        Args:
            message: 用户消息
            
        Returns:
            是否可缓存
        """
        message = message.strip()
        
        # 消息太长不缓存
        if len(message) > 20:
            return False
        
        patterns = self._compile_patterns()
        
        for pattern_type, compiled_list in patterns.items():
            for pattern in compiled_list:
                if pattern.match(message):
                    return True
        
        return False
    
    def get_message_type(self, message: str) -> Optional[str]:
        """
        获取消息类型
        
        Returns:
            "greeting", "acknowledgment", "farewell", or None
        """
        message = message.strip()
        patterns = self._compile_patterns()
        
        for pattern_type, compiled_list in patterns.items():
            for pattern in compiled_list:
                if pattern.match(message):
                    return pattern_type
        
        return None
    
    def _get_cache_key(self, message_pattern: str, affinity_state: str) -> str:
        """生成缓存键"""
        # 使用消息类型 + affinity_state 作为键
        return f"response_cache:{message_pattern}:{affinity_state}"
    
    async def get_cached_response(
        self,
        message: str,
        affinity_state: str
    ) -> Optional[str]:
        """
        获取缓存的响应
        
        Args:
            message: 用户消息
            affinity_state: 好感度状态
            
        Returns:
            缓存的响应，如果没有则返回 None
        """
        message_type = self.get_message_type(message)
        
        if not message_type:
            return None
        
        # 首先尝试从 Redis 获取
        if self.redis:
            try:
                cache_key = self._get_cache_key(message_type, affinity_state)
                cached = await self.redis.get(cache_key)
                
                if cached:
                    data = json.loads(cached)
                    # 更新命中计数
                    data["hit_count"] = data.get("hit_count", 0) + 1
                    await self.redis.setex(cache_key, self.ttl, json.dumps(data))
                    
                    logger.info(f"Cache hit for {message_type}/{affinity_state}")
                    return data["response"]
                    
            except Exception as e:
                logger.warning(f"Redis cache get failed: {e}")
        
        # 从预设模板获取
        response = self._get_preset_response(message_type, affinity_state)
        
        if response:
            # 缓存响应
            await self.cache_response(message_type, affinity_state, response)
        
        return response
    
    def _get_preset_response(
        self,
        message_type: str,
        affinity_state: str
    ) -> Optional[str]:
        """从预设模板获取响应"""
        import random
        
        templates = {
            "greeting": self.GREETING_RESPONSES,
            "acknowledgment": self.ACKNOWLEDGMENT_RESPONSES,
            "farewell": self.FAREWELL_RESPONSES,
        }
        
        type_templates = templates.get(message_type, {})
        state_responses = type_templates.get(affinity_state, type_templates.get("stranger", []))
        
        if state_responses:
            return random.choice(state_responses)
        
        return None
    
    async def cache_response(
        self,
        message_pattern: str,
        affinity_state: str,
        response: str,
        ttl: Optional[int] = None
    ) -> None:
        """
        缓存响应
        
        Args:
            message_pattern: 消息模式/类型
            affinity_state: 好感度状态
            response: 响应内容
            ttl: 过期时间（秒）
        """
        if not self.redis:
            return
        
        try:
            cache_key = self._get_cache_key(message_pattern, affinity_state)
            data = {
                "response": response,
                "affinity_state": affinity_state,
                "hit_count": 1,
                "created_at": datetime.now().isoformat(),
            }
            
            await self.redis.setex(
                cache_key,
                ttl or self.ttl,
                json.dumps(data)
            )
            
            logger.debug(f"Cached response for {message_pattern}/{affinity_state}")
            
        except Exception as e:
            logger.warning(f"Redis cache set failed: {e}")
    
    async def invalidate_cache(
        self,
        message_pattern: Optional[str] = None,
        affinity_state: Optional[str] = None
    ) -> int:
        """
        使缓存失效
        
        Args:
            message_pattern: 消息模式（可选，为空则清除所有）
            affinity_state: 好感度状态（可选）
            
        Returns:
            删除的缓存数量
        """
        if not self.redis:
            return 0
        
        try:
            if message_pattern and affinity_state:
                # 删除特定缓存
                cache_key = self._get_cache_key(message_pattern, affinity_state)
                return self.redis.delete(cache_key)
            else:
                # 删除所有响应缓存
                pattern = "response_cache:*"
                keys = self.redis.keys(pattern)
                if keys:
                    return self.redis.delete(*keys)
                return 0
                
        except Exception as e:
            logger.warning(f"Redis cache invalidate failed: {e}")
            return 0
    
    async def get_cache_stats(self) -> dict:
        """获取缓存统计信息"""
        stats = {
            "total_keys": 0,
            "total_hits": 0,
            "by_type": {},
        }
        
        if not self.redis:
            return stats
        
        try:
            pattern = "response_cache:*"
            keys = self.redis.keys(pattern)
            stats["total_keys"] = len(keys)
            
            for key in keys:
                cached = self.redis.get(key)
                if cached:
                    data = json.loads(cached)
                    hit_count = data.get("hit_count", 0)
                    stats["total_hits"] += hit_count
                    
                    # 解析 key 获取类型
                    parts = key.decode() if isinstance(key, bytes) else key
                    parts = parts.split(":")
                    if len(parts) >= 2:
                        msg_type = parts[1]
                        if msg_type not in stats["by_type"]:
                            stats["by_type"][msg_type] = {"keys": 0, "hits": 0}
                        stats["by_type"][msg_type]["keys"] += 1
                        stats["by_type"][msg_type]["hits"] += hit_count
                        
        except Exception as e:
            logger.warning(f"Failed to get cache stats: {e}")
        
        return stats
