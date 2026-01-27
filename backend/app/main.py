"""FastAPI 主应用入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import init_db, close_db, wait_for_postgres
from app.middleware.rate_limit import RateLimitMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Startup
    await wait_for_postgres()  # 等待数据库就绪
    await init_db()
    yield
    # Shutdown
    await close_db()


app = FastAPI(
    title="Affinity API",
    description="情感化 AI 陪伴记忆系统 - 基于 GraphRAG 与好感度演化",
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate Limiting 中间件
app.add_middleware(RateLimitMiddleware, requests_per_minute=100)

# 注册路由
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Welcome to Affinity API",
        "docs": "/docs",
        "health": "/health"
    }
