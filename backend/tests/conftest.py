"""Pytest 配置和 Fixtures"""
import pytest
import asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from app.main import app
from app.core.config import settings
from app.core.database import Base, get_db


# 测试数据库 URL
TEST_DATABASE_URL = settings.DATABASE_URL.replace("affinity", "affinity_test")


@pytest.fixture(scope="session")
def event_loop() -> Generator:
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def test_engine():
    """创建测试数据库引擎"""
    engine = create_async_engine(
        TEST_DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        echo=True
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    """创建测试数据库会话"""
    async_session = async_sessionmaker(
        test_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    async with async_session() as session:
        yield session
        await session.rollback()


@pytest.fixture
async def client(db_session) -> AsyncGenerator[AsyncClient, None]:
    """创建测试客户端"""
    
    async def override_get_db():
        yield db_session
    
    app.dependency_overrides[get_db] = override_get_db
    
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac
    
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict:
    """创建认证头"""
    from app.core.security import create_access_token
    
    token = create_access_token(data={"sub": "test-user-id"})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def sample_user_id() -> str:
    """示例用户 ID"""
    return "test-user-id"


@pytest.fixture
def sample_message() -> dict:
    """示例消息"""
    return {
        "message": "我妈妈最近身体不太好，有点担心。",
        "session_id": None,
        "idempotency_key": "test-key-001"
    }


@pytest.fixture
def sample_affinity_signals() -> dict:
    """示例好感度信号"""
    return {
        "user_initiated": True,
        "emotion_valence": 0.3,
        "memory_confirmation": False,
        "correction": False,
        "silence_days": 0
    }
