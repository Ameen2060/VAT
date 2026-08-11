"""Scheduled FTA source monitor.

Run periodically (e.g. a daily Render cron job): fetches every active official source,
detects content changes, and records them as NEW signals for human review. It shares the
same database as the API, so detected signals appear immediately in the FTA Updates UI.

    python -m app.tasks.monitor_cron
"""

from __future__ import annotations

from ..core.database import Base, SessionLocal, engine
from ..fta.monitor import check_all_sources
from ..fta.seed import seed_fta


def main() -> None:
    # Ensure tables exist and official sources are seeded (idempotent), then check.
    from .. import models  # noqa: F401 — register models on the metadata

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_fta(db)
        result = check_all_sources(db)
    print(
        f"FTA monitor: {result['checked']} checked, "
        f"{result['changed']} changed (new signals), {result['errors']} errors"
    )


if __name__ == "__main__":
    main()
