import argparse
import asyncio
import hashlib
import shutil
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.database import AsyncSessionLocal
from app.services.content_pool_manager_service import ContentPoolManagerService
from app.services.safety_screener_service import SafetyScreenerService


def _hash(text_description: str, image_url: str | None) -> str:
    normalized_url = (image_url or "").split("?")[0].split("#")[0].lower().strip()
    normalized_text = text_description.lower().strip()
    raw = f"{normalized_text}|{normalized_url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _infer_category(path: Path) -> str | None:
    parts = [p.lower() for p in path.parts]
    if any(k in parts for k in ["emotion", "情绪", "难过", "伤心", "哭"]):
        return "emotion"
    if any(k in parts for k in ["humor", "搞笑", "笑", "沙雕"]):
        return "humor"
    return None


async def _run(src_dir: Path, dest_dir: Path, limit: int):
    exts = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    files = [p for p in src_dir.rglob("*") if p.is_file() and p.suffix.lower() in exts]
    files = files[:limit] if limit > 0 else files

    dest_dir.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        pool_manager = ContentPoolManagerService(db)
        safety = SafetyScreenerService()

        created = 0
        approved = 0
        rejected = 0
        for p in files:
            text_description = p.stem.replace("_", " ").strip()
            if not text_description:
                continue

            filename = f"{hashlib.md5(str(p).encode('utf-8')).hexdigest()}{p.suffix.lower()}"
            target = dest_dir / filename
            if not target.exists():
                shutil.copy2(p, target)

            image_url = f"/static/memes/{filename}"
            content_hash = _hash(text_description, image_url)
            if await pool_manager.check_duplicate(content_hash):
                continue

            meme = await pool_manager.create_meme_candidate(
                text_description=text_description,
                source_platform="local",
                content_hash=content_hash,
                image_url=image_url,
                category=_infer_category(p),
                popularity_score=0.0,
                original_source_url=str(p)
            )
            created += 1

            screening = await safety.screen_meme(meme)
            if screening.overall_status == "approved":
                await pool_manager.update_meme_status(
                    meme.id,
                    "approved",
                    safety_status="approved",
                    safety_check_details=screening.to_dict()
                )
                await pool_manager.update_meme_trend(meme.id, 60.0, "rising")
                approved += 1
            elif screening.overall_status == "rejected":
                await pool_manager.update_meme_status(
                    meme.id,
                    "rejected",
                    safety_status="rejected",
                    safety_check_details=screening.to_dict()
                )
                rejected += 1
            else:
                await pool_manager.update_meme_status(
                    meme.id,
                    "flagged",
                    safety_status="flagged",
                    safety_check_details=screening.to_dict()
                )

        print("imported", created, "approved", approved, "rejected", rejected, "total_files", len(files))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--src_dir", required=True)
    parser.add_argument("--dest_dir", default=str(Path(__file__).resolve().parents[1] / "data" / "memes"))
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    src_dir = Path(args.src_dir)
    dest_dir = Path(args.dest_dir)
    asyncio.run(_run(src_dir, dest_dir, args.limit))


if __name__ == "__main__":
    main()
