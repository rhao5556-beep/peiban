"""API Schemas Package"""
from .meme import (
    MemeResponse,
    TrendingMemesResponse,
    MemeFeedbackRequest,
    MemeFeedbackResponse,
    MemeStatsResponse,
    MemeUsageHistoryResponse,
    UserMemePreferenceResponse,
    UserMemePreferenceUpdateRequest,
    MemeReportRequest,
    MemeReportResponse,
)

__all__ = [
    "MemeResponse",
    "TrendingMemesResponse",
    "MemeFeedbackRequest",
    "MemeFeedbackResponse",
    "MemeStatsResponse",
    "MemeUsageHistoryResponse",
    "UserMemePreferenceResponse",
    "UserMemePreferenceUpdateRequest",
    "MemeReportRequest",
    "MemeReportResponse",
]
