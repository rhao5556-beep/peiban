"""应用配置"""
from typing import List
from pydantic_settings import BaseSettings
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """应用配置类"""
    
    # 应用配置
    APP_NAME: str = "Affinity"
    DEBUG: bool = False
    
    # 数据库配置
    DATABASE_URL: str = "postgresql://affinity:affinity_secret@localhost:5432/affinity"
    
    # Redis 配置
    REDIS_URL: str = "redis://localhost:6379/0"
    
    # Neo4j 配置
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j_secret"
    
    # Milvus 配置
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "memories"
    
    # JWT 配置
    JWT_SECRET: str = "your-secret-key-change-in-production"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24  # 24 hours
    
    # LLM 配置 (支持 OpenAI 兼容 API，如硅基流动)
    OPENAI_API_KEY: str = ""
    OPENAI_API_BASE: str = "https://api.siliconflow.cn/v1"  # 硅基流动 API
    OPENAI_MODEL: str = "deepseek-ai/DeepSeek-V3"  # 默认模型

    # 网络/模型调用超时（秒）
    LLM_REQUEST_TIMEOUT_S: float = 30.0
    EMBEDDING_REQUEST_TIMEOUT_S: float = 20.0
    ENTITY_EXTRACTION_TIMEOUT_S: float = 0.8
    ENTITY_EXTRACTION_MODEL: str = "Qwen/Qwen2.5-7B-Instruct"

    LLM_STRICT_MODE: bool = False

    # 图谱事实检索降级配置
    GRAPH_FACTS_ENABLED: bool = True
    GRAPH_FACTS_TIMEOUT_S: float = 0.9
    
    # CORS 配置 (支持常见前端端口)
    CORS_ORIGINS: List[str] = [
        "http://localhost:3000",   # React CRA
        "http://localhost:5173",   # Vite
        "http://localhost:5174",   # Vite 备用
        "http://localhost:5175",   # Vite 备用
        "http://localhost:8000",   # 同源
        "http://127.0.0.1:5173",   # Vite (127.0.0.1)
        "http://127.0.0.1:5175",   # Vite (127.0.0.1)
    ]
    
    # Rate Limiting
    RATE_LIMIT_PER_MINUTE: int = 100
    
    # Outbox 配置
    OUTBOX_MAX_RETRIES: int = 5
    OUTBOX_BACKOFF_BASE: int = 2
    
    # SLO 配置
    SLO_MEDIAN_LAG_MS: int = 2000
    SLO_P95_LAG_MS: int = 30000
    
    # 表情包系统配置
    # 微博 API 配置（MVP：仅微博）
    WEIBO_API_KEY: str = ""
    WEIBO_API_BASE_URL: str = "https://api.weibo.com/2"
    
    # 表情包安全筛选
    MEME_SAFETY_SCREENING_ENABLED: bool = True
    
    # 表情包聚合频率（小时）
    MEME_SENSOR_INTERVAL_HOURS: int = 1
    
    # 表情包趋势更新频率（小时）
    MEME_TREND_UPDATE_INTERVAL_HOURS: int = 2
    
    # 表情包归档阈值（天数）
    MEME_ARCHIVAL_DECLINING_DAYS: int = 30
    
    # 表情包去重检查
    MEME_DUPLICATE_CHECK_ENABLED: bool = True

    # GIF/图片抓取（用于表情包动图）
    MEME_GIF_FETCH_ENABLED: bool = True
    MEME_GIF_FETCH_TIMEOUT_MS: int = 1500
    TENOR_API_KEY: str = ""
    TENOR_CLIENT_KEY: str = "affinity"
    TENOR_API_BASE_URL: str = "https://tenor.googleapis.com/v2"

    CONTENT_LIBRARY_IN_CONVERSATION_ENABLED: bool = False
    CONTENT_LIBRARY_IN_CONVERSATION_MAX_ITEMS: int = 2
    CONTENT_LIBRARY_IN_CONVERSATION_TIMEOUT_MS: int = 150
    
    class Config:
        env_file = str(Path(__file__).resolve().parents[2] / ".env")
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """获取配置单例"""
    return Settings()


settings = get_settings()
