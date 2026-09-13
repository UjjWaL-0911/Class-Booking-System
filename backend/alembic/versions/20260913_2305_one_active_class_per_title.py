"""One active class per title

Two classes called "Vinyasa Flow" are a data-entry mistake rather than a studio
with two of them, and the mistake is expensive: goal 3 schedules a session
against a class *by id*, so a duplicate silently splits a timetable in two.
Half the sessions hang off one row and half off the other, and every report
that groups by class — goal 8's breakdown especially — reads as though the
studio runs two half-popular classes instead of one busy one.

Three decisions are baked into the index, each arguable:

**Case-insensitive**, via ``lower(title)``. "Vinyasa Flow" and "vinyasa flow"
are one class to everybody except a byte comparison, and a constraint that
lets both exist is close to decorative — the same argument that makes
``users.email`` a ``citext``.

**Partial, on live classes only.** Archiving means "not offered any more", and
a name that is no longer offered should be reusable: a studio that retires
Hot Yoga and brings back something new by that name is doing normal business,
not making a mistake. This mirrors ``one_active_booking``, which likewise
constrains only the rows that are still live.

  The consequence is worth stating because it looks like a bug and is not: if
  the name has been taken since, **restoring an archived class fails**. That is
  the correct answer — restoring would otherwise produce exactly the duplicate
  this index exists to prevent — and the error layer turns it into a 409 that
  says which name is in the way.

**An index rather than application code.** The check has to be atomic with the
insert, and "SELECT then INSERT" is a race rather than a safeguard: two staff
adding the same class at the same moment would both find nothing and both
write. The database is the only place that check can be honest.

Revision ID: 02c00d7c0f5f
Revises: 3988495a7ebe
Create Date: 2026-09-13 23:05:00.731262
"""

from collections.abc import Sequence

from alembic import op

revision: str = "02c00d7c0f5f"
down_revision: str | Sequence[str] | None = "3988495a7ebe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "one_active_class_title"


def upgrade() -> None:
    # Raised as a readable error rather than left to the index, because the
    # index's own message names a row id and a studio does not think in uuids.
    # It also fires before anything is changed, so a migration that cannot apply
    # leaves the database exactly as it was.
    duplicates = op.get_bind().exec_driver_sql(
        """
        SELECT lower(title) AS title, count(*) AS n
        FROM classes
        WHERE archived_at IS NULL
        GROUP BY lower(title)
        HAVING count(*) > 1
        ORDER BY n DESC, title
        """
    ).fetchall()
    if duplicates:
        listed = ", ".join(f"{row.title!r} x{row.n}" for row in duplicates)
        raise RuntimeError(
            f"Cannot enforce unique class titles: {listed}. "
            "Archive or rename the duplicates first, then run this migration again."
        )

    op.execute(
        f"""
        CREATE UNIQUE INDEX {INDEX}
            ON classes (lower(title))
            WHERE archived_at IS NULL
        """
    )


def downgrade() -> None:
    op.execute(f"DROP INDEX IF EXISTS {INDEX}")
