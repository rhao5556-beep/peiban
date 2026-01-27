"""数据库连接管理"""
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import text
from neo4j import AsyncGraphDatabase
from pymilvus import connections, Collection
import redis.asyncio as redis

from app.core.config import settings


async def wait_for_postgres(max_retries: int = 30, delay: float = 2.0):
    """等待 PostgreSQL 就绪（带重试）"""
    for attempt in range(max_retries):
        try:
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
                print(f"✅ PostgreSQL connected (attempt {attempt + 1})")
                return True
        except Exception as e:
            print(f"⏳ Waiting for PostgreSQL... ({attempt + 1}/{max_retries}): {e}")
            await asyncio.sleep(delay)
    raise RuntimeError("❌ PostgreSQL connection failed after max retries")

# SQLAlchemy Base
Base = declarative_base()

# PostgreSQL 异步引擎
engine = create_async_engine(
    settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
    echo=settings.DEBUG,
    pool_size=10,
    max_overflow=20
)

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Neo4j 驱动
neo4j_driver = None

# Redis 客户端
redis_client = None

# Milvus 连接状态
milvus_connected = False


async def init_db():
    """初始化所有数据库连接"""
    global neo4j_driver, redis_client, milvus_connected
    
    # Neo4j
    neo4j_driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI,
        auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    
    # Redis
    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
    
    # Milvus
    try:
        connections.connect(
            alias="default",
            host=settings.MILVUS_HOST,
            port=settings.MILVUS_PORT
        )
        milvus_connected = True
        
        # 确保 collection 存在
        _ensure_milvus_collection()
        print("✅ Milvus connected and collection ready")
    except Exception as e:
        print(f"Milvus connection failed: {e}")
        milvus_connected = False


def _ensure_milvus_collection():
    """确保 Milvus collection 存在，不存在则创建"""
    from pymilvus import utility, FieldSchema, CollectionSchema, DataType
    
    collection_name = settings.MILVUS_COLLECTION
    
    # 检查 collection 是否存在
    if utility.has_collection(collection_name):
        # 检查 schema 是否正确（是否有 valence 字段）
        try:
            existing = Collection(collection_name)
            field_names = [f.name for f in existing.schema.fields]
            if "valence" not in field_names:
                print(f"⚠️ Milvus collection '{collection_name}' missing 'valence' field, recreating...")
                utility.drop_collection(collection_name)
            else:
                print(f"✅ Milvus collection '{collection_name}' already exists with correct schema")
                existing.load()
                return
        except Exception as e:
            print(f"⚠️ Error checking collection schema: {e}, recreating...")
            utility.drop_collection(collection_name)
    
    # 创建 collection schema
    # 使用 1024 维度（匹配 BAAI/bge-m3 模型）
    fields = [
        FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=64),
        FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64),
        FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1024),
        FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=4096),
        FieldSchema(name="valence", dtype=DataType.FLOAT),  # 情感值
        FieldSchema(name="created_at", dtype=DataType.INT64),
    ]
    
    schema = CollectionSchema(
        fields=fields,
        description="Memory embeddings for Affinity"
    )
    
    # 创建 collection
    collection = Collection(name=collection_name, schema=schema)
    
    # 创建索引
    index_params = {
        "metric_type": "COSINE",
        "index_type": "IVF_FLAT",
        "params": {"nlist": 128}
    }
    collection.create_index(field_name="embedding", index_params=index_params)
    
    # 加载到内存
    collection.load()
    
    print(f"✅ Created Milvus collection '{collection_name}' with 1024-dim vectors and valence field")


async def close_db():
    """关闭所有数据库连接"""
    global neo4j_driver, redis_client
    
    if neo4j_driver:
        await neo4j_driver.close()
    
    if redis_client:
        await redis_client.close()
    
    if milvus_connected:
        connections.disconnect("default")


async def get_db() -> AsyncSession:
    """获取数据库会话"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


def get_neo4j_driver():
    """获取 Neo4j 驱动"""
    return neo4j_driver


def get_redis_client():
    """获取 Redis 客户端"""
    return redis_client


def get_milvus_collection(name: str = None) -> Collection:
    """获取 Milvus Collection"""
    collection_name = name or settings.MILVUS_COLLECTION
    return Collection(collection_name)
