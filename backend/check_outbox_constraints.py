import sys

from sqlalchemy import create_engine, text

from app.core.config import settings


def main() -> int:
    engine = create_engine(settings.DATABASE_URL, pool_pre_ping=True)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT conname, pg_get_constraintdef(oid) AS def
                FROM pg_constraint
                WHERE conrelid = 'outbox_events'::regclass
                  AND contype = 'c'
                ORDER BY conname
                """
            )
        ).fetchall()
    for name, definition in rows:
        print(name)
        print(definition)
        print("-" * 60)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

