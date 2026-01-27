import argparse
import json
import sys
from datetime import datetime, timedelta

from sqlalchemy import create_engine, text

from app.core.config import settings
from app.worker.tasks.outbox import process_outbox_event


def _parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=200)
    p.add_argument("--reset_processing_minutes", type=int, default=10)
    p.add_argument("--include_failed", action="store_true")
    p.add_argument("--include_dlq", action="store_true")
    p.add_argument("--include_pending_review", action="store_true")
    p.add_argument("--dry_run", action="store_true")
    return p.parse_args()


def main():
    args = _parse_args()
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True, pool_size=1, max_overflow=0)

    statuses = ["pending"]
    if args.include_failed:
        statuses.append("failed")
    if args.include_dlq:
        statuses.append("dlq")
    if args.include_pending_review:
        statuses.append("pending_review")

    statuses_to_reset = [s for s in statuses if s != "pending"]

    reset_before = datetime.utcnow() - timedelta(minutes=args.reset_processing_minutes)

    with engine.connect() as conn:
        if args.reset_processing_minutes > 0 and not args.dry_run:
            conn.execute(
                text(
                    """
                    UPDATE outbox_events
                    SET status = 'pending'
                    WHERE status = 'processing' AND created_at < :cutoff
                    """
                ),
                {"cutoff": reset_before},
            )
            conn.commit()

        if not args.dry_run and statuses_to_reset:
            for st in statuses_to_reset:
                conn.execute(
                    text(
                        """
                        UPDATE outbox_events
                        SET status = 'pending'
                        WHERE status = :st
                        """
                    ),
                    {"st": st},
                )
            conn.commit()

        rows = conn.execute(
            text(
                """
                SELECT event_id, payload
                FROM outbox_events
                WHERE status = 'pending'
                ORDER BY created_at ASC
                LIMIT :limit
                """
            ),
            {"limit": args.limit},
        ).fetchall()

    if not rows:
        print("no_pending_events")
        return 0

    ok = 0
    failed = 0
    skipped = 0
    for idx, (event_id, payload) in enumerate(rows, start=1):
        payload_dict = json.loads(payload) if isinstance(payload, str) else payload
        if args.dry_run:
            print(f"dry_run {idx}/{len(rows)} {event_id}")
            continue
        try:
            res = process_outbox_event.apply(args=(event_id, payload_dict)).get()
            st = (res or {}).get("status")
            if st in ("success", "dlq"):
                ok += 1
            elif st == "skipped":
                skipped += 1
            else:
                failed += 1
            if idx % 20 == 0:
                print(f"progress {idx}/{len(rows)} ok={ok} failed={failed} skipped={skipped}")
        except Exception as e:
            failed += 1
            print(f"error {event_id} {type(e).__name__} {e}")

    print(f"done ok={ok} failed={failed} skipped={skipped} total={len(rows)}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
