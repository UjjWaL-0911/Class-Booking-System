"""Core schema: extensions, enum types, and the ten tables.

The first of three migrations that build the schema. This one is structural only —
tables, columns, foreign keys, plain indexes and check constraints. Everything the
ORM cannot express (the partial unique index, the GiST exclusion constraints, the
trigram indexes, and every trigger) lands in the next migration, and the
least-privilege application role in the one after that.

Splitting it three ways keeps each migration reviewable on its own and makes the
order of dependencies explicit: structure, then guarantees, then permissions.

Extensions are created here rather than in setup instructions because they are
per-database, not per-cluster — a fact that cost a confusing failure when the test
database had none and the development database did.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = 'deccce34d2c5'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EXTENSIONS = ("citext", "btree_gist", "pg_trgm")

ENUM_TYPES: dict[str, tuple[str, ...]] = {
    "user_role": ("staff", "instructor"),
    "booking_status": ("booked", "waitlisted", "cancelled", "attended", "no_show"),
    "booking_event_type": ("created", "status_changed", "note_added"),
}


def upgrade() -> None:
    for extension in EXTENSIONS:
        op.execute(f"CREATE EXTENSION IF NOT EXISTS {extension}")

    # Created explicitly rather than by SQLAlchemy's Enum(create_type=True), so the
    # migration owns the type's lifetime and a table can be dropped and recreated
    # without the type vanishing underneath another one.
    for type_name, labels in ENUM_TYPES.items():
        values = ", ".join(f"'{label}'" for label in labels)
        op.execute(f"CREATE TYPE {type_name} AS ENUM ({values})")

    op.create_table('classes',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('description', sa.Text(), server_default='', nullable=False),
    sa.Column('discipline', sa.Text(), nullable=False),
    sa.Column('default_duration_min', sa.Integer(), nullable=False),
    sa.Column('default_capacity', sa.Integer(), nullable=False),
    sa.Column('archived_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default='0', nullable=False),
    sa.CheckConstraint('default_capacity > 0', name=op.f('ck_classes_capacity_positive')),
    sa.CheckConstraint('default_duration_min > 0', name=op.f('ck_classes_duration_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_classes'))
    )
    op.create_table('members',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('full_name', sa.Text(), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('membership_expiry', sa.Date(), nullable=False),
    sa.Column('notes', sa.Text(), server_default='', nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_members')),
    sa.UniqueConstraint('email', name=op.f('uq_members_email'))
    )
    op.create_index('ix_members_expiry', 'members', ['membership_expiry'], unique=False)
    op.create_table('rooms',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_rooms')),
    sa.UniqueConstraint('name', name=op.f('uq_rooms_name'))
    )
    op.create_table('users',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('email', postgresql.CITEXT(), nullable=False),
    sa.Column('password_hash', sa.Text(), nullable=False),
    sa.Column('full_name', sa.Text(), nullable=False),
    sa.Column('role', postgresql.ENUM(name='user_role', create_type=False), nullable=False),
    sa.Column('is_active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('email', name=op.f('uq_users_email'))
    )
    op.create_table('membership_alert_dismissals',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('member_id', sa.Uuid(), nullable=False),
    sa.Column('dismissed_expiry', sa.Date(), nullable=False),
    sa.Column('dismissed_by', sa.Uuid(), nullable=False),
    sa.Column('dismissed_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['dismissed_by'], ['users.id'], name=op.f('fk_membership_alert_dismissals_dismissed_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('fk_membership_alert_dismissals_member_id_members'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_membership_alert_dismissals')),
    sa.UniqueConstraint('member_id', 'dismissed_expiry', name='uq_dismissal_member_expiry')
    )
    op.create_table('refresh_tokens',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('family_id', sa.Uuid(), nullable=False),
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('issued_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('revoked_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('replaced_by_id', sa.Uuid(), nullable=True),
    sa.Column('user_agent', sa.Text(), nullable=True),
    sa.Column('client_ip', postgresql.INET(), nullable=True),
    sa.ForeignKeyConstraint(['replaced_by_id'], ['refresh_tokens.id'], name=op.f('fk_refresh_tokens_replaced_by_id_refresh_tokens'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_refresh_tokens_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_refresh_tokens')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_refresh_tokens_token_hash'))
    )
    op.create_index('ix_refresh_tokens_active_user', 'refresh_tokens', ['user_id'], unique=False, postgresql_where=sa.text('revoked_at IS NULL'))
    op.create_index('ix_refresh_tokens_expiry', 'refresh_tokens', ['expires_at'], unique=False)
    op.create_index('ix_refresh_tokens_family', 'refresh_tokens', ['family_id'], unique=False)
    op.create_table('sessions',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('class_id', sa.Uuid(), nullable=False),
    sa.Column('starts_at', sa.TIMESTAMP(timezone=True), nullable=False),
    sa.Column('ends_at', sa.TIMESTAMP(timezone=True), server_default=sa.FetchedValue(), nullable=False),
    sa.Column('primary_instructor_id', sa.Uuid(), nullable=False),
    sa.Column('room_id', sa.Uuid(), nullable=False),
    sa.Column('duration_min', sa.Integer(), nullable=False),
    sa.Column('capacity', sa.Integer(), nullable=False),
    sa.Column('deleted_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.Integer(), server_default='0', nullable=False),
    sa.CheckConstraint('capacity > 0', name=op.f('ck_sessions_capacity_positive')),
    sa.CheckConstraint('duration_min > 0', name=op.f('ck_sessions_duration_positive')),
    sa.ForeignKeyConstraint(['class_id'], ['classes.id'], name=op.f('fk_sessions_class_id_classes'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['primary_instructor_id'], ['users.id'], name=op.f('fk_sessions_primary_instructor_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['room_id'], ['rooms.id'], name=op.f('fk_sessions_room_id_rooms'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions'))
    )
    op.create_index('ix_sessions_class', 'sessions', ['class_id'], unique=False)
    op.create_index('ix_sessions_starts_at', 'sessions', ['starts_at'], unique=False, postgresql_where='deleted_at IS NULL')
    op.create_table('bookings',
    sa.Column('id', sa.Uuid(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('member_id', sa.Uuid(), nullable=False),
    sa.Column('status', postgresql.ENUM(name='booking_status', create_type=False), nullable=False),
    sa.Column('booked_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('cancelled_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('settled_at', sa.TIMESTAMP(timezone=True), nullable=True),
    sa.Column('created_by', sa.Uuid(), nullable=False),
    sa.Column('settled_by', sa.Uuid(), nullable=True),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], name=op.f('fk_bookings_created_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['member_id'], ['members.id'], name=op.f('fk_bookings_member_id_members'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_bookings_session_id_sessions'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['settled_by'], ['users.id'], name=op.f('fk_bookings_settled_by_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_bookings'))
    )
    op.create_index('ix_bookings_booked_at', 'bookings', ['booked_at'], unique=False)
    op.create_index('ix_bookings_member', 'bookings', ['member_id'], unique=False)
    op.create_index('ix_bookings_session_status', 'bookings', ['session_id', 'status', 'booked_at'], unique=False)
    op.create_index('ix_bookings_status_booked_at', 'bookings', ['status', 'booked_at'], unique=False)
    op.create_table('session_co_instructors',
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('added_by', sa.Uuid(), nullable=False),
    sa.Column('added_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['added_by'], ['users.id'], name=op.f('fk_session_co_instructors_added_by_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_session_co_instructors_session_id_sessions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_session_co_instructors_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('session_id', 'user_id', name='pk_session_co_instructors')
    )
    op.create_index('ix_session_co_instructors_user', 'session_co_instructors', ['user_id'], unique=False)
    op.create_table('booking_events',
    sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
    sa.Column('booking_id', sa.Uuid(), nullable=False),
    sa.Column('event_type', postgresql.ENUM(name='booking_event_type', create_type=False), nullable=False),
    sa.Column('old_status', postgresql.ENUM(name='booking_status', create_type=False), nullable=True),
    sa.Column('new_status', postgresql.ENUM(name='booking_status', create_type=False), nullable=True),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('actor_user_id', sa.Uuid(), nullable=True),
    sa.Column('is_system', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('occurred_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['actor_user_id'], ['users.id'], name=op.f('fk_booking_events_actor_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['booking_id'], ['bookings.id'], name=op.f('fk_booking_events_booking_id_bookings'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_booking_events'))
    )
    op.create_index('ix_booking_events_booking', 'booking_events', ['booking_id', 'id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_booking_events_booking', table_name='booking_events')
    op.drop_table('booking_events')
    op.drop_index('ix_session_co_instructors_user', table_name='session_co_instructors')
    op.drop_table('session_co_instructors')
    op.drop_index('ix_bookings_status_booked_at', table_name='bookings')
    op.drop_index('ix_bookings_session_status', table_name='bookings')
    op.drop_index('ix_bookings_member', table_name='bookings')
    op.drop_index('ix_bookings_booked_at', table_name='bookings')
    op.drop_table('bookings')
    op.drop_index('ix_sessions_starts_at', table_name='sessions', postgresql_where='deleted_at IS NULL')
    op.drop_index('ix_sessions_class', table_name='sessions')
    op.drop_table('sessions')
    op.drop_index('ix_refresh_tokens_family', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_expiry', table_name='refresh_tokens')
    op.drop_index('ix_refresh_tokens_active_user', table_name='refresh_tokens', postgresql_where=sa.text('revoked_at IS NULL'))
    op.drop_table('refresh_tokens')
    op.drop_table('membership_alert_dismissals')
    op.drop_table('users')
    op.drop_table('rooms')
    op.drop_index('ix_members_expiry', table_name='members')
    op.drop_table('members')
    op.drop_table('classes')

    for type_name in ENUM_TYPES:
        op.execute(f"DROP TYPE IF EXISTS {type_name}")

    # Extensions are deliberately left in place: other schemas in the same database
    # may depend on them, and dropping a shared extension is not this migration's
    # decision to make.
