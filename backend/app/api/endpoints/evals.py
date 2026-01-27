import asyncio
import time
from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_user


router = APIRouter()


@router.get("/outbox/wait")
async def wait_outbox_drain(
    session_id: str = Query(..., min_length=8),
    timeout_s: float = Query(60.0, ge=0.1, le=600.0),
    poll_interval_ms: int = Query(200, ge=50, le=5000),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = current_user["user_id"]
    start = time.time()
    last_pending = None

    while True:
        result = await db.execute(
            text(
                """
                SELECT COUNT(*) AS c
                FROM outbox_events
                WHERE status IN ('pending', 'processing')
                  AND payload->>'conversation_id' = :sid
                  AND payload->>'user_id' = :uid
                """
            ),
            {"sid": session_id, "uid": user_id},
        )
        pending_count = int(result.scalar() or 0)
        last_pending = pending_count

        elapsed = time.time() - start
        if pending_count == 0:
            return {
                "ready": True,
                "pending_count": pending_count,
                "session_id": session_id,
                "user_id": user_id,
                "elapsed_s": round(elapsed, 3),
            }
        if elapsed >= timeout_s:
            return {
                "ready": False,
                "pending_count": pending_count,
                "session_id": session_id,
                "user_id": user_id,
                "elapsed_s": round(elapsed, 3),
            }

        await asyncio.sleep(poll_interval_ms / 1000.0)

