from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.core.database as database
from app.core.database import get_db, get_milvus_collection
from app.core.security import get_current_user
from app.services.retrieval_service import EmbeddingService


router = APIRouter()


class MemorizeRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4096)
    session_id: Optional[str] = None
    valence: Optional[float] = None


class MemorizeResponse(BaseModel):
    memory_id: str
    created_at: int


class MemorizeBatchRequest(BaseModel):
    contents: List[str] = Field(min_length=1)
    session_id: Optional[str] = None
    valences: Optional[List[float]] = None


class MemorizeBatchResponse(BaseModel):
    memory_ids: List[str]
    created_at: int


def _normalize_valences(valences: Optional[List[float]], n: int) -> List[float]:
    if not valences:
        return [0.0] * n
    out = [0.0] * n
    for i in range(min(n, len(valences))):
        try:
            out[i] = float(valences[i])
        except Exception:
            out[i] = 0.0
    return out


@router.post("/memorize", response_model=MemorizeResponse)
async def memorize(
    request: MemorizeRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not database.milvus_connected:
        raise HTTPException(status_code=503, detail="milvus_not_connected")

    user_id = str(current_user["user_id"])
    content = (request.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="empty_content")

    embedding_service = EmbeddingService()
    embedding = await embedding_service.encode(content)

    created_at = int(time.time())
    memory_id = str(uuid.uuid4())
    valence = float(request.valence) if request.valence is not None else 0.0

    collection = get_milvus_collection()
    collection.insert([[memory_id], [user_id], [embedding], [content], [valence], [created_at]])
    collection.flush()

    conv_id = None
    if request.session_id:
        try:
            conv_id = str(uuid.UUID(request.session_id))
        except ValueError:
            conv_id = None

    await db.execute(
        text(
            """
            INSERT INTO memories (id, user_id, content, embedding, valence, status, conversation_id, created_at, committed_at)
            VALUES (:id, :user_id, :content, NULL, :valence, 'committed', :conversation_id, NOW(), NOW())
            """
        ),
        {
            "id": memory_id,
            "user_id": user_id,
            "content": content,
            "valence": valence,
            "conversation_id": conv_id,
        },
    )
    await db.commit()

    return MemorizeResponse(memory_id=memory_id, created_at=created_at)


@router.post("/memorize_batch", response_model=MemorizeBatchResponse)
async def memorize_batch(
    request: MemorizeBatchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not database.milvus_connected:
        raise HTTPException(status_code=503, detail="milvus_not_connected")

    user_id = str(current_user["user_id"])
    contents = [str(x).strip() for x in (request.contents or [])]
    contents = [c for c in contents if c]
    if not contents:
        raise HTTPException(status_code=400, detail="empty_contents")
    if len(contents) > 512:
        raise HTTPException(status_code=400, detail="too_many_contents")

    embedding_service = EmbeddingService()
    embeddings = await embedding_service.encode_batch(contents)

    created_at = int(time.time())
    memory_ids = [str(uuid.uuid4()) for _ in contents]
    valences = _normalize_valences(request.valences, len(contents))
    created_ats = [created_at] * len(contents)

    collection = get_milvus_collection()
    collection.insert([memory_ids, [user_id] * len(contents), embeddings, contents, valences, created_ats])
    collection.flush()

    conv_id = None
    if request.session_id:
        try:
            conv_id = str(uuid.UUID(request.session_id))
        except ValueError:
            conv_id = None

    params: List[Dict[str, Any]] = []
    for mid, content, valence in zip(memory_ids, contents, valences):
        params.append(
            {
                "id": mid,
                "user_id": user_id,
                "content": content,
                "valence": float(valence),
                "conversation_id": conv_id,
            }
        )

    await db.execute(
        text(
            """
            INSERT INTO memories (id, user_id, content, embedding, valence, status, conversation_id, created_at, committed_at)
            VALUES (:id, :user_id, :content, NULL, :valence, 'committed', :conversation_id, NOW(), NOW())
            """
        ),
        params,
    )
    await db.commit()

    return MemorizeBatchResponse(memory_ids=memory_ids, created_at=created_at)

