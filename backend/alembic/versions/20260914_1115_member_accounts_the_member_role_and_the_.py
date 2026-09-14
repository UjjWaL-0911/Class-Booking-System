"""Member accounts: the member role and the link to a login

Self-service booking needs a member to *be* somebody the system can authenticate
and attribute writes to. This migration makes that possible without moving a
single existing row.

**Why the credentials go on ``users`` rather than on ``members``.** The note in
``models/member.py`` used to say this phase would add ``password_hash`` and
``last_login_at`` to ``members``. That plan does not survive contact with the
audit trail: every write records its actor as a foreign key into ``users`` —

    bookings.created_by            → users.id   NOT NULL
    bookings.settled_by            → users.id   nullable
    booking_events.actor_user_id   → users.id   nullable

— so a member who books their own place would have nothing valid to put in
``created_by``. Fixing that from the ``members`` side means teaching the
append-only timeline about a second species of actor, which is the most
expensive place in this schema to add a concept and the one place it can never
be revised later.

So a member who opts into self-service gets a ``users`` row with
``role = 'member'``, and ``members.user_id`` points at it. Members without an
account keep ``user_id IS NULL`` and are completely unaffected; ``bookings``
still references ``members.id`` and never moves, which is the half of the
original note that was right.

**Nothing here rejects anything**, which is deliberate. A new enum label and a
nullable column are invisible to code that does not know about them, so this can
be applied to a running deployment before the code that uses it — the opposite
of ``one_active_class_title``, which refused duplicates and therefore had to
follow its code. Additive first, constraining second.

Revision ID: bf4a255ee580
Revises: 02c00d7c0f5f
Create Date: 2026-09-14 11:15:48.917499
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "bf4a255ee580"
down_revision: str | Sequence[str] | None = "02c00d7c0f5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # PostgreSQL 12+ allows ALTER TYPE ... ADD VALUE inside a transaction, but the
    # new label cannot be *used* in that same transaction. This migration only
    # adds it; the first row carrying it is written by a later request, so the
    # restriction never bites. IF NOT EXISTS keeps a re-run harmless.
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'member'")

    op.add_column("members", sa.Column("user_id", sa.Uuid(), nullable=True))

    # RESTRICT, like every other foreign key into `users`: an account is
    # deactivated rather than deleted, because deleting one would orphan the
    # bookings and audit rows that name it as the actor.
    op.create_foreign_key(
        "fk_members_user_id_users",
        "members",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    # One login belongs to at most one member. A partial unique index rather than
    # a UNIQUE constraint because the column is overwhelmingly null — every member
    # the studio has ever added by hand — and those nulls should cost nothing.
    op.execute(
        """
        CREATE UNIQUE INDEX one_member_per_login
            ON members (user_id)
            WHERE user_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS one_member_per_login")
    op.drop_constraint("fk_members_user_id_users", "members", type_="foreignkey")
    op.drop_column("members", "user_id")
    # The enum label is deliberately left in place. Removing a value from a
    # PostgreSQL enum means rebuilding the type and every column using it, and a
    # label nothing references is inert. Reversing this migration should not be a
    # riskier operation than applying it was.
