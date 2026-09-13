"""Instructor session rate for payroll

What a person is paid for teaching one session, in **minor units** — paise, pence,
cents. An integer, never a float: money in a float is a rounding error waiting for a
year-end total, and 1250 is unambiguous in a way that 12.50 stored as a double is
not. No currency column, because the studio has one currency for the same reason it
has one timezone; a second studio is a migration either way.

Nullable, and null is meaningful rather than zero. An instructor with no rate set has
not been given one, and the payroll report says so instead of quietly reporting that
they are owed nothing — those are different facts and only one of them is safe to
act on.

Revision ID: 3988495a7ebe
Revises: 1fbf47163293
Create Date: 2026-09-13 17:39:53.507404
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3988495a7ebe"
down_revision: str | Sequence[str] | None = "1fbf47163293"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("session_rate_minor", sa.Integer(), nullable=True),
    )
    # A negative rate is not a discount, it is a typo. The check costs nothing and
    # means the payroll query never has to defend against one.
    op.create_check_constraint(
        "session_rate_minor_not_negative",
        "users",
        "session_rate_minor IS NULL OR session_rate_minor >= 0",
    )


def downgrade() -> None:
    # The bare name, not the expanded one: the naming convention in db/base.py
    # prefixes it, and passing the already-prefixed name gets it prefixed twice.
    # Only a downgrade hits this, which is exactly why it went unnoticed until
    # the seed's --reset ran one.
    op.drop_constraint("session_rate_minor_not_negative", "users", type_="check")
    op.drop_column("users", "session_rate_minor")
