"""Seed the database with demo data.

    python -m app.seed            # seed an empty database
    python -m app.seed --reset    # drop everything, migrate, then seed

``--reset`` exists because this data cannot be cleanly removed: ``booking_events``
rejects DELETE and TRUNCATE by design, so the only way back to a clean slate is to
drop the schema and migrate it again.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from app.core.config import Environment, get_settings
from app.db.engine import build_engine, build_session_factory
from app.seed.data import DEMO_PASSWORD
from app.seed.runner import Seeder, is_seeded


def _reset_schema() -> None:
    """Drop to base and migrate back up.

    Alembic is invoked in-process rather than as a subprocess so it picks up the
    same configuration this script already validated.
    """
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")


async def _seed(reset: bool) -> int:
    settings = get_settings()

    if settings.environment is Environment.PRODUCTION and reset:
        # Dropping the schema is not something to offer a production database, and
        # the flag is one keystroke away from the safe form of the command.
        print("Refusing to --reset a production database.", file=sys.stderr)
        return 2

    if reset:
        print("Dropping and re-migrating the schema...")
        _reset_schema()

    engine = build_engine(settings)
    factory = build_session_factory(engine)
    try:
        async with factory() as db:
            if await is_seeded(db):
                print(
                    "This database already contains demo data. "
                    "Use --reset to rebuild it from scratch.",
                    file=sys.stderr,
                )
                return 1

            print("Seeding...")
            summary = await Seeder(db, settings).run()
    finally:
        await engine.dispose()

    print(
        f"\n  {summary.users} accounts, {summary.members} members, "
        f"{summary.rooms} rooms, {summary.classes} classes"
        f"\n  {summary.sessions} sessions in {settings.studio_timezone}, "
        f"{summary.co_instructors} with a co-instructor"
        f"\n  {summary.bookings} booked, {summary.waitlisted} waitlisted, "
        f"{summary.cancelled} cancelled, {summary.settled} settled"
    )
    for note in summary.notes[:3]:
        print(f"  - {note}")

    print("\nSign in with any of these and the password below:")
    print("  manager@studio.demo    (staff)")
    print("  frontdesk@studio.demo  (staff)")
    print("  aryan@studio.demo      (instructor)")
    print("  marcus@studio.demo     (instructor)")
    print("  elena@studio.demo      (instructor)")
    print(f"\n  password: {DEMO_PASSWORD}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the demo studio.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop the schema and migrate it again before seeding.",
    )
    args = parser.parse_args()
    return asyncio.run(_seed(args.reset))


if __name__ == "__main__":
    raise SystemExit(main())
