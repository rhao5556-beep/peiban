import asyncio
import os
import sys
from sqlalchemy import text

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.database import engine


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("ALTER TABLE memories ADD COLUMN IF NOT EXISTS meta JSONB DEFAULT '{}'::jsonb"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS idx_memories_meta_gin ON memories USING gin (meta)"))


if __name__ == "__main__":
    asyncio.run(main())
