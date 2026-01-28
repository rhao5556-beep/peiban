"""评测辅助端点"""
import asyncio
import time
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.core.security import get_current_user
from app.core.database import get_db
from app.core.ids import normalize_uuid


router = APIRouter()


@router.get("/outbox/wait")
async def wait_outbox_committed(
    session_id: str,
    timeout_s: int = 60,
    poll_interval_ms: int = 200,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user_id = normalize_uuid(current_user["user_id"])
    session_id = normalize_uuid(session_id)

    deadline = time.monotonic() + max(1, int(timeout_s))
    poll_s = max(0.05, poll_interval_ms / 1000.0)

    last_state = None
    while True:
        memories_row = (
            await db.execute(
                text(
                    """
                    SELECT
                        COUNT(*) FILTER (WHERE status = 'committed') AS committed_count,
                        COUNT(*) AS total_count
                    FROM memories
                    WHERE user_id::text = :user_id
                      AND conversation_id::text = :conversation_id
                    """
                ),
                {"user_id": user_id, "conversation_id": session_id},
            )
        ).fetchone()

        committed_count = int(memories_row[0] or 0)
        total_count = int(memories_row[1] or 0)

        outbox_row = (
            await db.execute(
                text(
                    """
                    SELECT
                        COUNT(*) AS outbox_total,
                        COUNT(*) FILTER (WHERE o.status IN ('pending', 'processing')) AS outbox_inflight
                    FROM outbox_events o
                    JOIN memories m ON m.id::text = o.memory_id::text
                    WHERE m.user_id::text = :user_id
                      AND m.conversation_id::text = :conversation_id
                    """
                ),
                {"user_id": user_id, "conversation_id": session_id},
            )
        ).fetchone()

        outbox_total = int(outbox_row[0] or 0)
        outbox_inflight = int(outbox_row[1] or 0)

        ready = committed_count > 0 and ((outbox_total == 0) or (outbox_inflight == 0))

        last_state = {
            "ready": ready,
            "session_id": session_id,
            "user_id": user_id,
            "committed_memories_count": committed_count,
            "total_memories_count": total_count,
            "outbox_total_count": outbox_total,
            "outbox_inflight_count": outbox_inflight,
        }

        if ready:
            return {**last_state, "timeout": False}

        if time.monotonic() >= deadline:
            return {**last_state, "timeout": True}

        await asyncio.sleep(poll_s)
