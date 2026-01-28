"""API 路由聚合"""
from fastapi import APIRouter

from app.api.endpoints import (
    conversation, memory, affinity, graph, auth, sse, metrics, profile,
    content_recommendation, meme, proactive, evals
)

api_router = APIRouter()

# 认证路由
api_router.include_router(auth.router, prefix="/auth", tags=["认证"])

# 对话路由
api_router.include_router(conversation.router, prefix="/conversation", tags=["对话"])

# 记忆路由
api_router.include_router(memory.router, prefix="/memories", tags=["记忆"])

# 好感度路由
api_router.include_router(affinity.router, prefix="/affinity", tags=["好感度"])

# 图谱路由
api_router.include_router(graph.router, prefix="/graph", tags=["图谱"])

# SSE 流式路由
api_router.include_router(sse.router, prefix="/sse", tags=["流式"])

# 评测辅助路由
api_router.include_router(evals.router, prefix="/evals", tags=["评测"])

# 用户画像路由
api_router.include_router(profile.router, prefix="/users", tags=["用户画像"])

# 内容推荐路由
api_router.include_router(content_recommendation.router, tags=["内容推荐"])

# 表情包路由
api_router.include_router(meme.router, prefix="/memes", tags=["表情包"])

# 主动消息路由
api_router.include_router(proactive.router, prefix="/proactive", tags=["主动消息"])

# 监控路由（无需认证）
api_router.include_router(metrics.router, tags=["监控"])
