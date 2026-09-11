"""Guarantees: the constraints, indexes and triggers the ORM cannot express.

Everything here is a rule the database enforces itself, so that it holds no matter
which code path runs — including one written later that forgets to check. In rough
order of importance:

* ``one_active_booking`` — a member cannot hold two places on one session. Also
  what turns a double-submitted booking into a clean 409 rather than a duplicate.
* two GiST exclusion constraints — no room and no *primary* instructor is ever
  double-booked. Co-instructors are deliberately exempt (goal 5).
* ``booking_events`` immutability — goal 9 says even studio staff cannot edit the
  timeline, so it cannot rest on nobody writing an UPDATE later.
* the capacity backstop — see the long comment on it below; the obvious version of
  this trigger does not work.
* ``ends_at`` and ``updated_at`` maintenance, and the alert-dismissal reset.

Revision ID: 1fbf47163293
Revises: deccce34d2c5
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "1fbf47163293"
down_revision: str | None = "deccce34d2c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    _create_functions()
    _create_triggers()
    _create_constraints()
    _create_indexes()


def downgrade() -> None:
    _drop_indexes()
    _drop_constraints()
    _drop_triggers()
    _drop_functions()


# --------------------------------------------------------------------------- functions


def _create_functions() -> None:
    # updated_at is maintained here as well as by the ORM's onupdate, because it
    # must be right on every path — including a migration or a manual fix applied
    # with psql, neither of which goes through SQLAlchemy.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $fn$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END;
        $fn$ LANGUAGE plpgsql;
        """
    )

    # ends_at is derived, but cannot be a generated column: those require an
    # IMMUTABLE expression and `timestamptz + interval` is only STABLE, because an
    # interval's day and month components resolve against the session TimeZone
    # setting. Verified on PostgreSQL 18.6 — "generation expression is not immutable".
    #
    # The trigger fires on every UPDATE rather than only when starts_at or
    # duration_min change, so an UPDATE that sets ends_at directly is corrected too.
    # Without that it would be possible to desynchronise the column from the data it
    # is derived from, and with it the GiST index built on top of it.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_session_ends_at() RETURNS trigger AS $fn$
        BEGIN
            NEW.ends_at := NEW.starts_at + make_interval(mins => NEW.duration_min);
            RETURN NEW;
        END;
        $fn$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE OR REPLACE FUNCTION reject_mutation() RETURNS trigger AS $fn$
        BEGIN
            RAISE EXCEPTION 'booking_events is append-only'
                USING ERRCODE = 'restrict_violation';
        END;
        $fn$ LANGUAGE plpgsql;
        """
    )

    # The capacity backstop. The application never oversells a session, because
    # every booking-affecting operation counts Booked rows while holding
    # SELECT ... FOR UPDATE on the session row. This exists so that a future code
    # path which forgets that lock still cannot oversell.
    #
    # The obvious implementation is wrong, and it is worth recording why. A deferred
    # constraint trigger that merely runs count(*) at commit is NOT race-safe: it
    # executes inside the committing transaction under READ COMMITTED, so its count
    # sees only already-committed rows plus its own. Two transactions that both
    # skipped the row lock would each count the capacity, each pass, and both commit
    # — precisely the scenario this is meant to catch. It would only ever have caught
    # a single-threaded logic error, while reading like a concurrency guarantee.
    #
    # Taking the lock inside the trigger is what makes it real.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION enforce_session_capacity() RETURNS trigger AS $fn$
        DECLARE
            v_capacity int;
            v_booked   int;
        BEGIN
            -- Serialise against any other transaction touching this session's
            -- bookings. On the normal path the caller already holds this lock, so
            -- re-taking it costs nothing.
            SELECT capacity INTO v_capacity
              FROM sessions WHERE id = NEW.session_id FOR UPDATE;

            SELECT count(*) INTO v_booked
              FROM bookings
             WHERE session_id = NEW.session_id AND status = 'booked';

            IF v_booked > v_capacity THEN
                RAISE EXCEPTION
                    'session % oversold: % booked, capacity %',
                    NEW.session_id, v_booked, v_capacity
                    USING ERRCODE = 'check_violation',
                          -- Without CONSTRAINT the field is null and the error can
                          -- only be matched on message text. The error-mapping layer
                          -- dispatches on constraint name, so the name must be set.
                          CONSTRAINT = 'bookings_capacity_check';
            END IF;
            RETURN NULL;
        END;
        $fn$ LANGUAGE plpgsql;
        """
    )

    # Goal 10's re-trigger rule is carried by the dismissal row storing the expiry
    # value that was current when it was dismissed, so a new later date simply has
    # no matching dismissal. This closes the one case that misses: dismiss, extend
    # the expiry, then correct it back to the original date — where the old row
    # would match again and suppress an alert for a genuinely expired member.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION clear_alert_dismissals() RETURNS trigger AS $fn$
        BEGIN
            DELETE FROM membership_alert_dismissals WHERE member_id = NEW.id;
            RETURN NULL;
        END;
        $fn$ LANGUAGE plpgsql;
        """
    )


def _drop_functions() -> None:
    for fn in (
        "clear_alert_dismissals",
        "enforce_session_capacity",
        "reject_mutation",
        "set_session_ends_at",
        "set_updated_at",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {fn}()")


# ---------------------------------------------------------------------------- triggers

_UPDATED_AT_TABLES = ("users", "classes", "sessions", "members")


def _create_triggers() -> None:
    for table in _UPDATED_AT_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER {table}_set_updated_at
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION set_updated_at()
            """
        )

    op.execute(
        """
        CREATE TRIGGER sessions_set_ends_at
            BEFORE INSERT OR UPDATE ON sessions
            FOR EACH ROW EXECUTE FUNCTION set_session_ends_at()
        """
    )

    op.execute(
        """
        CREATE TRIGGER booking_events_no_row_change
            BEFORE UPDATE OR DELETE ON booking_events
            FOR EACH ROW EXECUTE FUNCTION reject_mutation()
        """
    )
    # Row-level triggers do not fire on TRUNCATE, which would otherwise empty an
    # "append-only" table in a single statement.
    op.execute(
        """
        CREATE TRIGGER booking_events_no_truncate
            BEFORE TRUNCATE ON booking_events
            FOR EACH STATEMENT EXECUTE FUNCTION reject_mutation()
        """
    )

    # WHEN keeps this off every transition that is not a move into 'booked'. Without
    # it, deleting a session — which cancels every remaining booking — would run one
    # count(*) per cancelled row at commit time.
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER bookings_capacity_check
            AFTER INSERT OR UPDATE ON bookings
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW
            WHEN (NEW.status = 'booked')
            EXECUTE FUNCTION enforce_session_capacity()
        """
    )

    op.execute(
        """
        CREATE TRIGGER members_expiry_clears_dismissals
            AFTER UPDATE OF membership_expiry ON members
            FOR EACH ROW
            WHEN (NEW.membership_expiry IS DISTINCT FROM OLD.membership_expiry)
            EXECUTE FUNCTION clear_alert_dismissals()
        """
    )


def _drop_triggers() -> None:
    drops: list[tuple[str, str]] = [
        ("members", "members_expiry_clears_dismissals"),
        ("bookings", "bookings_capacity_check"),
        ("booking_events", "booking_events_no_truncate"),
        ("booking_events", "booking_events_no_row_change"),
        ("sessions", "sessions_set_ends_at"),
    ]
    drops += [(t, f"{t}_set_updated_at") for t in _UPDATED_AT_TABLES]
    for table, trigger in drops:
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")


# ------------------------------------------------------------------------- constraints


def _create_constraints() -> None:
    # No two live sessions overlap in the same room, or for the same primary
    # instructor. Co-instructors are exempt: goal 5 allows one instructor to be
    # added to any number of sessions, including overlapping ones.
    #
    # Both need btree_gist, for the `=` operator class on uuid.
    op.execute(
        """
        ALTER TABLE sessions ADD CONSTRAINT no_room_overlap
            EXCLUDE USING gist (
                room_id WITH =,
                tstzrange(starts_at, ends_at) WITH &&
            ) WHERE (deleted_at IS NULL)
        """
    )
    op.execute(
        """
        ALTER TABLE sessions ADD CONSTRAINT no_primary_instructor_overlap
            EXCLUDE USING gist (
                primary_instructor_id WITH =,
                tstzrange(starts_at, ends_at) WITH &&
            ) WHERE (deleted_at IS NULL)
        """
    )


def _drop_constraints() -> None:
    for name in ("no_primary_instructor_overlap", "no_room_overlap"):
        op.execute(f"ALTER TABLE sessions DROP CONSTRAINT IF EXISTS {name}")


# ----------------------------------------------------------------------------- indexes


def _create_indexes() -> None:
    # One active booking per member per session. A partial unique index rather than
    # a table constraint, because the rule applies only to the two active statuses:
    # a member may be cancelled from a session and then booked onto it again.
    op.execute(
        """
        CREATE UNIQUE INDEX one_active_booking
            ON bookings (session_id, member_id)
            WHERE status IN ('booked', 'waitlisted')
        """
    )

    # Goal 6's text search over member name and email.
    #
    # The email index is built on (email::text), and the query must cast the same
    # way. A trigram index *can* be created directly on a citext column — but the
    # planner will not use it for citext-native operators. Measured on 20,000 rows:
    # `email ILIKE '%x%'` sequentially scans, `email::text ILIKE '%x%'` uses the
    # index. The results are identical either way, so the mistake is invisible
    # everywhere except the query plan.
    op.execute(
        "CREATE INDEX ix_members_name_trgm ON members USING gin (full_name gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_members_email_trgm ON members "
        "USING gin ((email::text) gin_trgm_ops)"
    )


def _drop_indexes() -> None:
    for name in ("ix_members_email_trgm", "ix_members_name_trgm", "one_active_booking"):
        op.execute(f"DROP INDEX IF EXISTS {name}")
