import asyncio
import hashlib
from datetime import datetime
import sys
from pathlib import Path

from sqlalchemy import select

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal
from app.models.meme import Meme


def _hash(text_description: str, image_url: str | None) -> str:
    normalized_url = (image_url or "").split("?")[0].split("#")[0].lower().strip()
    normalized_text = text_description.lower().strip()
    raw = f"{normalized_text}|{normalized_url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def main():
    seeds = [
        {"text_description": "无语", "category": "emotion"},
        {"text_description": "笑死", "category": "humor"},
        {"text_description": "破防了", "category": "emotion"},
        {"text_description": "我真的会谢", "category": "humor"},
        {"text_description": "yyds 永远的神", "category": "trending_phrase"},
    ]

    async with AsyncSessionLocal() as db:
        created = 0
        for item in seeds:
            text_description = item["text_description"]
            image_url = None
            content_hash = _hash(text_description, image_url)

            existing = await db.execute(select(Meme).where(Meme.content_hash == content_hash))
            if existing.scalar_one_or_none():
                continue

            meme = Meme(
                image_url=image_url,
                text_description=text_description,
                source_platform="local",
                category=item.get("category"),
                content_hash=content_hash,
                original_source_url=None,
                popularity_score=0.0,
                trend_score=80.0,
                trend_level="hot",
                safety_status="approved",
                safety_check_details={"seed": True, "created_at": datetime.utcnow().isoformat()},
                status="approved",
                usage_count=0,
            )
            db.add(meme)
            created += 1

        await db.commit()
        print("seeded", created)


if __name__ == "__main__":
    asyncio.run(main())
