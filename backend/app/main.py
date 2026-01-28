"""FastAPI 主应用入口"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import init_db, close_db, wait_for_postgres
from app.core.tracing import init_tracing
from app.core.startup_checks import validate_production_settings
from app.middleware.rate_limit import RateLimitMiddleware
from app.middleware.api_version import ApiVersionMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Startup
    validate_production_settings(settings)
    await wait_for_postgres()  # 等待数据库就绪
    init_tracing(app, service_name=settings.APP_NAME)
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
allowed_methods = ["*"] if settings.DEBUG else ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
allowed_headers = ["*"] if settings.DEBUG else ["Authorization", "Content-Type", "X-Token-Issue-Secret"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=allowed_methods,
    allow_headers=allowed_headers,
)

# API 版本标识
app.add_middleware(ApiVersionMiddleware, default_version="v1")

app.add_middleware(RateLimitMiddleware, requests_per_minute=100)

# 注册路由
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "version": "0.1.0"}


@app.get("/health/full")
async def health_full():
    from app.core.database import engine, get_neo4j_driver, get_redis_client, milvus_connected
    from sqlalchemy import text

    neo4j_ok = False
    neo4j_err = None
    try:
        driver = get_neo4j_driver()
        if driver:
            async with driver.session() as session:
                res = await session.run("RETURN 1 AS ok")
                await res.single()
            neo4j_ok = True
    except Exception as e:
        neo4j_err = f"{e.__class__.__name__}: {e}"

    redis_ok = False
    redis_err = None
    beat_ok = False
    try:
        r = get_redis_client()
        if r:
            await r.ping()
            redis_ok = True
            beat_ok = bool(await r.get("celerybeat:heartbeat"))
    except Exception as e:
        redis_err = f"{e.__class__.__name__}: {e}"

    postgres_ok = False
    postgres_err = None
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        postgres_ok = True
    except Exception as e:
        postgres_err = f"{e.__class__.__name__}: {e}"

    milvus_ok = False
    milvus_err = None
    try:
        if milvus_connected:
            from pymilvus import utility

            milvus_ok = utility.has_collection(settings.MILVUS_COLLECTION)
            if not milvus_ok:
                milvus_err = f"collection_not_found:{settings.MILVUS_COLLECTION}"
        else:
            milvus_err = "not_connected"
    except Exception as e:
        milvus_err = f"{e.__class__.__name__}: {e}"

    overall_ok = postgres_ok and redis_ok and neo4j_ok and milvus_ok
    return {
        "status": "healthy" if overall_ok else "degraded",
        "version": "0.1.0",
        "deps": {
            "postgres": {"ok": postgres_ok, "error": postgres_err},
            "redis": {"ok": redis_ok, "error": redis_err},
            "celerybeat": {"ok": beat_ok},
            "neo4j": {"ok": neo4j_ok, "error": neo4j_err},
            "milvus": {"ok": milvus_ok, "connected": bool(milvus_connected), "error": milvus_err},
        },
    }


@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Welcome to Affinity API",
        "docs": "/docs",
        "health": "/health"
    }
