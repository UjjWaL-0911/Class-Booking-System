"""Alembic environment.

Two deliberate differences from the generated template:

* **The URL comes from application settings, not alembic.ini.** Connection details
  are secrets and belong in the environment, so ``alembic.ini`` carries no URL at
  all and there is nothing to accidentally commit.

* **Migrations run on psycopg (sync), not asyncpg.** They connect as the *owner*
  through the session-mode pooler, while the application connects as ``app_rw``
  through the transaction pooler. Session mode is required because DDL and
  transaction pooling do not mix, and because Supabase's direct endpoint is
  IPv6-only and unreachable from Render.
"""

from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import make_url

from alembic import context
from app.core.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _migration_url() -> str:
    """The owner connection, forced onto the psycopg driver."""
    url = make_url(get_settings().migration_database_url)
    if url.drivername in ("postgresql", "postgres"):
        url = url.set(drivername="postgresql+psycopg")
    return url.render_as_string(hide_password=False)


def include_object(obj: object, name: str | None, type_: str, *_: object) -> bool:
    """Keep autogenerate away from objects it cannot see or should not own.

    ``app_rw`` is a role, not a table, and the triggers, exclusion constraints and
    partial indexes in this schema are hand-written SQL that autogenerate would
    try to drop on every run because it cannot reflect them faithfully.
    """
    if type_ == "table" and name in {"spatial_ref_sys"}:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_migration_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _migration_url()

    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
            # Every migration runs in one transaction, so a failure leaves the
            # schema untouched rather than half-applied.
            transaction_per_migration=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
