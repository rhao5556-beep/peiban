"""表情包API模型 - Pydantic Schemas"""
from typing import Optional, List
from pydantic import BaseModel, Field, HttpUrl, field_validator
from datetime import datetime
from uuid import UUID


class MemeResponse(BaseModel):
    """表情包响应模型
    
    用于返回单个表情包的详细信息
    """
    id: str
    image_url: Optional[str] = None  # MVP阶段纯文本表情包可为空
    text_description: str
    source_platform: str  # 'weibo', 'douyin', 'bilibili'
    category: Optional[str] = None  # 'humor', 'emotion', 'trending_phrase'
    trend_score: float = Field(ge=0.0, le=100.0, description="趋势分数 (0-100)")
    trend_level: str  # 'emerging', 'rising', 'hot', 'peak', 'declining'
    usage_count: int = Field(ge=0, description="使用次数")
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "image_url": None,
                "text_description": "yyds 永远的神",
                "source_platform": "weibo",
                "category": "trending_phrase",
                "trend_score": 85.5,
                "trend_level": "peak",
                "usage_count": 42
            }
        }


class TrendingMemesResponse(BaseModel):
    """热门表情包列表响应模型
    
    用于GET /api/v1/memes/trending端点
    """
    memes: List[MemeResponse]
    total: int = Field(ge=0, description="返回的表情包总数")
    
    class Config:
        json_schema_extra = {
            "example": {
                "memes": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "image_url": None,
                        "text_description": "yyds 永远的神",
                        "source_platform": "weibo",
                        "category": "trending_phrase",
                        "trend_score": 85.5,
                        "trend_level": "peak",
                        "usage_count": 42
                    }
                ],
                "total": 1
            }
        }


class MemeFeedbackRequest(BaseModel):
    """表情包反馈请求模型
    
    用于POST /api/v1/memes/feedback端点
    用户对表情包使用提供反馈
    """
    usage_id: str = Field(description="使用记录ID (UUID格式)")
    reaction: str = Field(description="用户反应: liked, ignored, disliked")
    
    @field_validator('reaction')
    @classmethod
    def validate_reaction(cls, v: str) -> str:
        """验证反应类型必须是允许的值之一"""
        allowed_reactions = {'liked', 'ignored', 'disliked'}
        if v not in allowed_reactions:
            raise ValueError(
                f"reaction must be one of {allowed_reactions}, got '{v}'"
            )
        return v
    
    @field_validator('usage_id')
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        """验证UUID格式"""
        try:
            UUID(v)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {v}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "usage_id": "550e8400-e29b-41d4-a716-446655440000",
                "reaction": "liked"
            }
        }


class MemeFeedbackResponse(BaseModel):
    """表情包反馈响应模型
    
    确认反馈已记录
    """
    success: bool
    message: str
    usage_id: Optional[str] = None  # 使用历史记录ID
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Feedback recorded successfully",
                "usage_id": "789e0123-e89b-12d3-a456-426614174000"
            }
        }


class MemeStatsResponse(BaseModel):
    """表情包统计响应模型
    
    用于GET /api/v1/memes/stats端点
    返回表情包系统的整体统计信息
    """
    total_memes: int = Field(ge=0, description="表情包总数")
    approved_memes: int = Field(ge=0, description="已批准的表情包数量")
    trending_memes: int = Field(ge=0, description="热门表情包数量 (hot/peak)")
    acceptance_rate: float = Field(ge=0.0, le=1.0, description="接受率 (0-1)")
    avg_trend_score: float = Field(ge=0.0, le=100.0, description="平均趋势分数")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_memes": 150,
                "approved_memes": 120,
                "trending_memes": 25,
                "acceptance_rate": 0.68,
                "avg_trend_score": 45.3
            }
        }


class MemeUsageHistoryResponse(BaseModel):
    """表情包使用历史响应模型
    
    用于返回用户的表情包使用历史
    """
    id: str
    user_id: str
    meme_id: str
    conversation_id: str
    used_at: datetime
    user_reaction: Optional[str] = None  # 'liked', 'ignored', 'disliked'
    meme: Optional[MemeResponse] = None  # 可选包含表情包详情
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "789e0123-e89b-12d3-a456-426614174000",
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "meme_id": "550e8400-e29b-41d4-a716-446655440000",
                "conversation_id": "456e7890-e89b-12d3-a456-426614174000",
                "used_at": "2024-01-15T10:30:00Z",
                "user_reaction": "liked"
            }
        }


class UserMemePreferenceResponse(BaseModel):
    """用户表情包偏好响应模型
    
    用于返回用户的表情包使用偏好设置
    """
    user_id: str
    meme_enabled: bool = Field(description="是否启用表情包功能")
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "user_id": "123e4567-e89b-12d3-a456-426614174000",
                "meme_enabled": True,
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }


class UserMemePreferenceUpdateRequest(BaseModel):
    """用户表情包偏好更新请求模型
    
    用于PUT /api/v1/memes/preferences端点
    """
    meme_enabled: bool = Field(description="是否启用表情包功能")
    
    class Config:
        json_schema_extra = {
            "example": {
                "meme_enabled": False
            }
        }


class MemeReportRequest(BaseModel):
    """表情包举报请求模型
    
    用于用户举报不当表情包
    """
    meme_id: str = Field(description="表情包ID (UUID格式)")
    reason: str = Field(description="举报原因", min_length=1, max_length=500)
    
    @field_validator('meme_id')
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        """验证UUID格式"""
        try:
            UUID(v)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {v}")
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "meme_id": "550e8400-e29b-41d4-a716-446655440000",
                "reason": "包含不当内容"
            }
        }


class MemeReportResponse(BaseModel):
    """表情包举报响应模型"""
    success: bool
    message: str
    report_id: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Report submitted successfully",
                "report_id": "999e0123-e89b-12d3-a456-426614174000"
            }
        }
