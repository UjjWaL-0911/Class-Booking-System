# Schema

PostgreSQL through SQLAlchemy 2.0 (async) with Alembic. Ten tables.

One sentence shaped all of it: **the database should make the studio's promises true, not store the
application's notes.** A rule that must hold whatever code runs — no member holding two places in one
class, no audit row ever edited, no two classes in one room — lives in Postgres, where a migration, a
script and a developer at a `psql` prompt all hit it equally. Rules needing a count or a sentence
explaining a refusal stay in the application (§3).

Four consequences: **no stored counts** (a counter is what drifts under concurrency), **an append-only
log beside a queryable status column**, **one studio, one timezone**, applied explicitly in every
date-bucketed query, and **seams left for later** — the audit log's actor is nullable so an automatic
change has somewhere to sit, and `members` was never folded into `users`.

**Where it runs.** Designed against local **PostgreSQL 18.6**, deployed on **Supabase 17.6**. All five
migrations applied unchanged in six seconds — extensions, both GiST exclusion constraints, the
immutability triggers. I checked the last by attempting a `TRUNCATE` against the live database and
watching it refuse, because a guarantee nobody has tried on the real platform is a guarantee on paper.
Nothing here needs a feature newer than 17.

## Conventions

- **`uuid` primary keys**, `gen_random_uuid` — a sequential integer in a URL tells anyone who looks
  how many members the studio has. `booking_events` is the exception: a `bigint` sequence, because an
  audit log wants strictly increasing order with a deterministic tiebreak.
- **Every timestamp is `timestamptz`, stored UTC.** Date bucketing converts explicitly with
  `AT TIME ZONE :studio_tz` rather than trusting the server — four goals are wrong together if it
  silently defaults.
- **`created_at` / `updated_at`** on `users`, `classes`, `sessions`, `members`, trigger-maintained so
  they are right whichever path wrote. `bookings` has neither: its mutations are status transitions,
  and `booking_events` records those with more precision.
- **`version integer`** on `classes` and `sessions` — optimistic-lock token, so the second of two
  stale edit forms gets a 409 rather than silently overwriting the first.
- **Soft delete only where history needs it:** `sessions.deleted_at`; `classes.archived_at`, which is
  restorable and deliberately a different word.
- **Three enums:** `user_role` (`staff`, `instructor`, `member`), `booking_status` (`booked`,
  `waitlisted`, `cancelled`, `attended`, `no_show`), `booking_event_type`. `no_show` reads as
  **Absent** wherever a person sees it, via a `label` property; the stored value stays `no_show`,
  because renaming an enum to fix wording is a migration in exchange for nothing.
- **Extensions:** `citext`, `btree_gist`, `pg_trgm`.
- **Two partial unique indexes** carry rules a plain constraint cannot: `one_active_booking` (below),
  and `one_active_class_title` on `lower(title) WHERE archived_at IS NULL` — case-insensitive for the
  same reason `email` is `citext`, partial because a retired name should be reusable.

**Where a member's password lives, and why it is not on `members`.** This document used to say the
self-service phase would add `password_hash` there. It cannot: every write names its actor as a foreign
key into `users` — `bookings.created_by` (not null), `bookings.settled_by`, `booking_events.actor_user_id`
— so a member booking their own place would have had nothing valid for `created_by`. Solving it from the
`members` side means teaching the append-only timeline about two species of actor, in the one table this
schema can never revise. A `users` row with `role='member'` and one nullable `members.user_id` costs less
and pays a dividend: goal 9 distinguishes "the member booked themselves" from "the desk booked them" with
no new column at all. Decision 5.

---

# Every schema question I had to settle

The whole document in one table. Everything below is the reasoning behind a row of it.

| Question | Decision | Reason |
|---|---|---|
| `members.email` uniqueness | Unique | A returning customer keeps one record |
| Where a member's password lives | On `users`, joined by `members.user_id` | Every actor column is an FK into `users`; the alternative rewrites the append-only log |
| Who can be `primary_instructor_id` | Any active teaching user | A staff member who teaches is a real case |
| Deleting a session with bookings | Soft delete, auto-cancel, audit event each | History must survive and every removal needs an actor |
| Booking onto an archived class | Rejected; existing bookings unaffected | Archived means "not offered", not "orphan the booked" |
| Two classes with one title | Rejected among live classes, case-insensitively | A duplicate splits one timetable across two rows |
| Capacity reduced below booked | Rejected with a message | Silent oversell is worse; explicit cancellations leave events |
| Capacity increased with a waitlist | Auto-promote, bounded by the new capacity | A free seat must never sit idle beside somebody waiting |
| Promoting an expired member | Skip, leave Waitlisted, `note_added` event | Promotion would let them in by a side door; skipping keeps their place |
| Promotion after the session started | Nobody | A seat freeing mid-class means nothing |
| "No-shows this week" | By session date, studio timezone | Matches how staff think about a week |
| "Currently waitlisted" | Future sessions only | Avoids a metric that can only grow, with no job |
| Total match count | `count(*) OVER ` in the same statement | One round trip, and it cannot disagree with the page |
| Capacity backstop | Deferred trigger **that takes the session lock** | A plain deferred `count(*)` is not race-safe — a false guarantee |
| `ends_at` | Trigger, firing on every update | Generated columns need IMMUTABLE; `timestamptz + interval` is STABLE |
| `updated_at` vs `version` | Trigger vs application code | `updated_at` must be right on every path; the optimistic check belongs where the update is written |
| Alert dismissal re-trigger | Keyed to the expiry value, plus a clearing trigger | Value-keying handles the normal case with no job; the trigger closes the revert hole |
| Refresh tokens | Own table, opaque, hashed, grouped into families | Rotation and revocation are impossible with a stateless token |
| Application database role | None — the app connects as owner | A least-privilege role was built and removed; the triggers already satisfy goal 9 |

---

# Q1 — The tables

## Who signs in

### `users`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `email` | citext | NOT NULL, **UNIQUE** (`uq_users_email`) |
| `password_hash` | text | NOT NULL (argon2id) |
| `full_name` | text | NOT NULL |
| `role` | user_role | NOT NULL |
| `is_active` | boolean | NOT NULL, default `true` |
| `session_rate_minor` | integer | NULL, CHECK `>= 0` |
| `created_at` / `updated_at` | timestamptz | NOT NULL; `updated_at` trigger-maintained |

**Accounts are never deleted.** An instructor who leaves still taught classes, and that history must keep
naming them — so leaving is `is_active = false`, and every FK pointing here from `sessions`, `bookings`,
`session_co_instructors` and `members` is `ON DELETE RESTRICT`. `refresh_tokens` is the exception and
cascades, because those rows are login state, not history.

`is_active` does real work: the access token is stateless and lasts fifteen minutes, but every
authenticated request loads this row, so clearing the flag locks somebody out immediately. A round trip
per request, traded deliberately for instant revocation.

`email` is `citext`, so `Ada@` and `ada@` are one person. `session_rate_minor` is the only money here:
an **integer in minor units**, because money in a float is a rounding error waiting for a year-end total.
No currency column — one studio, one currency. **Null is not zero**: it means no rate has been set, which
the payroll report says out loud rather than quietly reporting somebody is owed nothing.

### `refresh_tokens`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `user_id` | uuid | NOT NULL, FK → `users(id)` **ON DELETE CASCADE** |
| `family_id` | uuid | NOT NULL — one login lineage |
| `token_hash` | text | NOT NULL, **UNIQUE** — SHA-256 of the opaque token |
| `issued_at` / `expires_at` | timestamptz | NOT NULL |
| `revoked_at` | timestamptz | NULL |
| `replaced_by_id` | uuid | NULL, FK → self, **ON DELETE SET NULL** |
| `user_agent` / `client_ip` | text / inet | NULL |

```sql
CREATE INDEX ix_refresh_tokens_family      ON refresh_tokens (family_id);
CREATE INDEX ix_refresh_tokens_active_user ON refresh_tokens (user_id) WHERE revoked_at IS NULL;
CREATE INDEX ix_refresh_tokens_expiry      ON refresh_tokens (expires_at);
```

This table exists because **you cannot revoke a JWT**. The token is an opaque random string whose whole
job is to be looked up and revoked; only its hash is stored.

**`replaced_by_id` is `ON DELETE SET NULL`, and that one word matters.** With the default, pruning expired
rows fails with a foreign-key violation the moment a surviving row points at a pruned predecessor — the
normal case for any active session, so pruning would pass in a test and fail in production.

## What the studio offers

### `rooms`

`id` uuid PK · `name` text NOT NULL UNIQUE · `created_at` timestamptz.

A table rather than a text column on `sessions`: overlap detection joins on `room_id` and needs a stable
identity, and free text drifts into "Studio A" / "studio a" / "Studio-A" within a month.

### `classes`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `title` · `description` · `discipline` | text | NOT NULL (`description` defaults `''`) |
| `default_duration_min` · `default_capacity` | integer | NOT NULL, CHECK `> 0` |
| `archived_at` | timestamptz | NULL = active |
| `version` | integer | NOT NULL, default `0` |
| `created_at` / `updated_at` | timestamptz | NOT NULL |

The `default_` columns are starting values a session copies and may then change.

**Archiving is not deleting**, which is goal 2's actual requirement. Setting `archived_at` hides the class
from default views; every session and booking stays where it was, and restoring is clearing the column.
What it changes is that a *new* booking on an archived class is refused — existing ones are untouched,
because archiving must not strand somebody who already has a place.

## When it happens

### `sessions`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `class_id` · `primary_instructor_id` · `room_id` | uuid | NOT NULL, FK, ON DELETE RESTRICT |
| `starts_at` | timestamptz | NOT NULL |
| `ends_at` | timestamptz | NOT NULL, trigger-maintained |
| `duration_min` · `capacity` | integer | NOT NULL, CHECK `> 0` |
| `deleted_at` | timestamptz | NULL |
| `version` | integer | NOT NULL, default `0` |
| `created_at` / `updated_at` | timestamptz | NOT NULL |

```sql
CREATE INDEX ix_sessions_starts_at ON sessions (starts_at) WHERE deleted_at IS NULL;
CREATE INDEX ix_sessions_class     ON sessions (class_id);

ALTER TABLE sessions ADD CONSTRAINT no_room_overlap
  EXCLUDE USING gist (room_id WITH =, tstzrange(starts_at, ends_at) WITH &&)
  WHERE (deleted_at IS NULL);

ALTER TABLE sessions ADD CONSTRAINT no_primary_instructor_overlap
  EXCLUDE USING gist (primary_instructor_id WITH =, tstzrange(starts_at, ends_at) WITH &&)
  WHERE (deleted_at IS NULL);
```

`duration_min` and `capacity` are **copied** from the class and independent afterwards — the brief
requires per-session overrides, and copy-on-write gets them without a later class edit rewriting history.
`primary_instructor_id` may be **any active teaching user**, not only `role='instructor'`; a staff member
who teaches on Thursdays is a real studio, checked in the application because a CHECK cannot read another
table.

**Exclusion constraints rather than unique indexes**, because the thing excluded is an *overlap* rather
than an equality. Co-instructors are exempt — goal 5 explicitly allows one instructor on any number of
sessions. Both map by constraint name to a 409.

**`ends_at` is a trigger, not a generated column.** Generated columns need an **IMMUTABLE** expression
and `timestamptz + interval` is only **STABLE**, because an interval's day and month parts resolve against
a timezone. The trigger fires on every insert *and* update — not `UPDATE OF starts_at, duration_min` — so
an update writing `ends_at` directly is corrected too. The tempting shortcut, marking a wrapper
`IMMUTABLE` anyway, works for minute intervals and lies to the planner, which can silently corrupt an
index built on it.

**Deleting** sets `deleted_at` and, with the row locked in the same transaction, cancels every active
booking with an `is_system` event. Application logic rather than a cascade because **each cancellation
must leave an audit row**, and a cascade deletes silently.

**Capacity is the one field participating in the booking invariant**, so editing it takes the same
`FOR UPDATE` a booking takes — *before* reading the row, so the `version` check validates against a row
nobody else can be changing. Raising it promotes from the waitlist, bounded by the new capacity: raising
capacity creates seats exactly as a cancellation does.

### `session_co_instructors`

`session_id` uuid FK ON DELETE CASCADE · `user_id` uuid FK ON DELETE RESTRICT · `added_by` uuid FK ·
`added_at` timestamptz · **PK `(session_id, user_id)`**.

The composite key stops the same person being added twice. Cascading on `session_id` is safe — these rows
carry no history once the session is gone. Cascading on `user_id` would not be, hence `RESTRICT`.
`added_by` is recorded because "who put this instructor on my class" is a question somebody eventually
asks.

## Who comes

### `members`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `full_name` | text | NOT NULL |
| `email` | citext | NOT NULL, **UNIQUE** (`uq_members_email`) |
| `membership_expiry` | date | NOT NULL |
| `notes` | text | NOT NULL, default `''` |
| `user_id` | uuid | NULL, FK → `users(id)` ON DELETE RESTRICT, unique where present |
| `created_at` / `updated_at` | timestamptz | NOT NULL |

```sql
CREATE INDEX ix_members_name_trgm  ON members USING gin (full_name gin_trgm_ops);
CREATE INDEX ix_members_email_trgm ON members USING gin ((email::text) gin_trgm_ops);
CREATE INDEX ix_members_expiry     ON members (membership_expiry);
CREATE UNIQUE INDEX one_member_per_login ON members (user_id) WHERE user_id IS NOT NULL;
```

A member is a **customer record, and an account only where the desk has switched one on** — `user_id` is
null for everybody added by hand, which is most of them. Keeping members out of `users` is what made
self-service additive: one nullable column, and `bookings.member_id` never moved.

`membership_expiry` is a `date` because a membership runs out at the end of a day in the studio's
timezone — expired when `membership_expiry < current_date` in studio time, so still valid *on* the expiry
date.

**The `::text` cast, and the bug I nearly shipped.** I assumed the cast made the index *creatable* on
`citext`. It does not — `USING gin (email gin_trgm_ops)` succeeds. The real problem is one step further:
the planner will not use a trigram index for a **citext-native** operator, so you get an index that
exists, reports as valid, and is never used. Measured on PG 18.6, 20,000 rows, `enable_seqscan = off`:

| Predicate | Plan |
|---|---|
| `email ILIKE '%…%'` | Seq Scan — index ignored |
| `full_name ILIKE '%…%'` (control, plain `text`) | Bitmap Index Scan |

So the index is built on `(email::text)` **and the query casts too**. A planner that silently ignores an
index is worse than one that errors.

### `membership_alert_dismissals`

`id` uuid PK · `member_id` uuid FK **ON DELETE CASCADE** · `dismissed_by` uuid FK → `users` ·
`expiry_on_dismissal` date NOT NULL · `dismissed_at` timestamptz · **UNIQUE `(member_id, expiry_on_dismissal)`**.

The design turns on which value is stored: **the expiry as it was when dismissed**. An alert is suppressed
only while a dismissal matches the member's *present* expiry, so setting a new date leaves no match and the
alert reappears by itself once that date enters the seven-day window. Goal 10's re-trigger requirement
needs no background job and no per-member flag — it falls out of the key.

A trigger additionally clears these rows whenever the expiry changes at all, closing the one case
value-matching misses: dismiss, extend, then correct back to the original date.

## The booking, and the record of it

### `bookings`

| Column | Type | Constraints |
|---|---|---|
| `id` | uuid | PK |
| `session_id` · `member_id` | uuid | NOT NULL, FK, ON DELETE RESTRICT |
| `status` | booking_status | NOT NULL |
| `booked_at` | timestamptz | NOT NULL, default `now` |
| `cancelled_at` · `settled_at` | timestamptz | NULL |
| `created_by` | uuid | NOT NULL, FK → `users(id)` |
| `settled_by` | uuid | NULL, FK → `users(id)` |

```sql
CREATE UNIQUE INDEX one_active_booking ON bookings (session_id, member_id)
  WHERE status IN ('booked', 'waitlisted');

CREATE INDEX ix_bookings_session_status   ON bookings (session_id, status, booked_at);
CREATE INDEX ix_bookings_status_booked_at ON bookings (status, booked_at);
CREATE INDEX ix_bookings_booked_at        ON bookings (booked_at);
CREATE INDEX ix_bookings_member           ON bookings (member_id);
```

`booked_at` is written once and never changes. It does two jobs: goal 6's "sort by booked time", and
**the waitlist order** — first come, first served, as a column rather than a policy somebody could change.

**`one_active_booking` is partial, and the `WHERE` is the whole point.** One member holds one live place
on a session, but may book, cancel and book again — and each cancelled row must survive for the audit
trail. A plain unique constraint would forbid the second booking. It also turns a double-clicked submit
into a clean 409, which is why there is no idempotency-key table anywhere in this system.

**Who gets promoted.** Promotion happens in exactly two places — a cancellation, or capacity raised —
and never as a direct action, because a promotion endpoint would be a way around capacity. Waitlisted
bookings in `booked_at, id` order; the first whose membership has not expired takes the seat, an expired
one is skipped and left Waitlisted with a `note_added` event recording that a seat was offered and passed
over. A started session promotes nobody.

**The capacity backstop, and the version of it that would have been a lie.** The application never
oversells: every operation that can change the Booked count holds the session lock while counting. A
database backstop is still worth having for a future path that forgets — but the obvious implementation is
wrong, and *why* is the most interesting thing in this schema. A deferred trigger that merely runs
`count(*)` at commit executes **inside the committing transaction** under `READ COMMITTED`, so it sees
committed rows plus its own: two transactions that both skipped the lock each count, each pass, and both
commit. It would catch a single-threaded logic error while *reading* like a concurrency guarantee — worse
than no backstop. So the trigger takes the lock itself:

```sql
CREATE FUNCTION enforce_session_capacity RETURNS trigger AS $$
DECLARE v_capacity int; v_booked int;
BEGIN
  -- Serialise against anyone else touching this session's bookings. On the normal
  -- path the caller already holds this lock, so it is a no-op.
  SELECT capacity INTO v_capacity FROM sessions WHERE id = NEW.session_id FOR UPDATE;
  SELECT count(*) INTO v_booked
    FROM bookings WHERE session_id = NEW.session_id AND status = 'booked';
  IF v_booked > v_capacity THEN
    RAISE EXCEPTION 'session % oversold: % booked, capacity %',
      NEW.session_id, v_booked, v_capacity
      USING ERRCODE = 'check_violation', CONSTRAINT = 'bookings_capacity_check';
  END IF;
  RETURN NULL;
END; $$ LANGUAGE plpgsql;

CREATE CONSTRAINT TRIGGER bookings_capacity_check
  AFTER INSERT OR UPDATE ON bookings
  DEFERRABLE INITIALLY DEFERRED FOR EACH ROW
  WHEN (NEW.status = 'booked') EXECUTE FUNCTION enforce_session_capacity;
```

Two details. The `WHEN` clause filters rather than a column list, because it is evaluated at
modification time rather than at deferred firing — without it, soft-deleting a session with forty bookings
runs forty `count(*)` queries at commit. And this error is deliberately **not** in the application's error
map, so it surfaces as a 500: it should be unreachable, and a 500 with an alert is the right response to an
invariant the lock was supposed to guarantee.

### `booking_events` — the timeline that cannot be rewritten (goal 9)

| Column | Type | Constraints |
|---|---|---|
| `id` | bigint | PK, `BIGSERIAL` |
| `booking_id` | uuid | NOT NULL, FK → `bookings(id)` ON DELETE RESTRICT |
| `event_type` | booking_event_type | NOT NULL |
| `old_status` · `new_status` | booking_status | NULL |
| `note` | text | NULL |
| `actor_user_id` | uuid | NULL, FK → `users(id)` |
| `is_system` | boolean | NOT NULL, default `false` |
| `occurred_at` | timestamptz | NOT NULL, default `now` |

```sql
CREATE FUNCTION reject_mutation RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'booking_events is append-only' USING ERRCODE = 'restrict_violation';
END; $$ LANGUAGE plpgsql;

CREATE TRIGGER booking_events_no_row_change BEFORE UPDATE OR DELETE ON booking_events
  FOR EACH ROW EXECUTE FUNCTION reject_mutation;

-- Row triggers do not fire on TRUNCATE. This closes that hole.
CREATE TRIGGER booking_events_no_truncate BEFORE TRUNCATE ON booking_events
  FOR EACH STATEMENT EXECUTE FUNCTION reject_mutation;

CREATE INDEX ix_booking_events_booking ON booking_events (booking_id, id);
```

`actor_user_id` is nullable precisely so `is_system` means something: when a cancellation promotes the next
person, nobody did that, and writing the cancelling staff member's name would be a small permanent lie in
an audit log. Since members got accounts, the same column distinguishes a member booking themselves from
the desk booking them, with nothing new added. An earlier draft had a `metadata jsonb` column; I dropped
it, because an unstructured escape hatch in an append-only table is where schema discipline goes to die.

Two triggers rather than one, because `TRUNCATE` is table-level and a row guard leaves the whole log one
statement from deletion. These hold for **any** client — the API, a migration, a developer at `psql` —
which is the difference between a guarantee and a convention.

**A least-privilege `app_rw` role was built and deleted.** It worked, and went, because the triggers
achieve goal 9 alone while the role cost a second credential and a migration creating a login role on a
managed platform. The honest consequence: the app connects as owner, an owner cannot revoke privileges
from itself, and the triggers are therefore the entire guarantee — which I am comfortable with precisely
because they are database triggers rather than application code.

**What the guarantee costs.** The suite cannot reset between runs, so 415 tests share one accumulating
database and a test querying a whole table rather than its own rows passes once and fails afterwards. The
only clean slate is dropping the schema and migrating again. Mistakes are corrected by appending: a note
on the wrong booking stays, with a second note saying so.

---

# Q2 — Relationships

**One-to-many**

| Parent | Child | Foreign key |
|---|---|---|
| `classes` | `sessions` | `class_id` |
| `sessions` | `bookings` | `session_id` |
| `members` | `bookings` | `member_id` |
| `bookings` | `booking_events` | `booking_id` |
| `rooms` | `sessions` | `room_id` |
| `users` | `sessions` | `primary_instructor_id` |
| `users` | `bookings` | `created_by`, `settled_by` |
| `users` | `booking_events` | `actor_user_id` |
| `users` | `session_co_instructors` | `user_id`, `added_by` |
| `users` | `refresh_tokens` | `user_id` |
| `users` | `members` | `user_id` — at most one member per login |
| `members` | `membership_alert_dismissals` | `member_id` |
| `users` | `membership_alert_dismissals` | `dismissed_by` |

**Many-to-many** — exactly one: `sessions` ↔ `users` as co-instructors, through `session_co_instructors`.

A session relates to instructors **both** ways at once: one primary (one-to-many) and any number of
co-instructors (many-to-many). Goal 5's "one list of every session I am involved in" is the union, written
once as `visible_sessions_clause(user)` and composed into every session and booking query — a second copy
of a visibility rule is a second place for it to be wrong.

---

# Q3 — Database vs application

| Enforced in the **database** | Enforced in the **application**, inside the booking transaction |
|---|---|
| All foreign keys, NOT NULL | The booking state machine, each refusal carrying its reason |
| `users.email` / `members.email` uniqueness | Booked vs Waitlisted |
| One active booking per member per session | Waitlist promotion order and eligibility |
| One live class per title, case-insensitively | Membership expiry, at creation **and** at promotion |
| `capacity > 0`, `duration_min > 0`, enum validity | The archived-class check |
| Room and instructor non-overlap (GiST) | Capacity **reduction** — no DB backstop, see below |
| Booked count ≤ capacity **on writes to `bookings`** | "Has this session started" gates |
| Audit-log immutability | Row-level access on writes |
| `updated_at` and `ends_at` correctness | The `version` optimistic-lock check |
| Dismissals cleared when expiry changes | |

**The test I applied: would this rule still need to be true if the application were replaced tomorrow?**
If yes, the database — never two active bookings for one member, never a mutated audit row, never two
classes in one room. Those are properties of the studio rather than of my Python, and a rule living in one
service is one forgotten call site from being false. If it needs a row count, session context or a
sentence explaining itself, the application: *"This member's membership expired on 12 August"* is not
something a CHECK can say.

**Capacity sits on the line, with an asymmetry worth naming.** The decision lives in the application under
a row lock, where it can produce a good message and choose Booked or Waitlisted, with the lock-taking
deferred trigger behind it. But that trigger fires on `bookings`, so it catches overselling by *adding
bookings* and not by *reducing capacity* — which is why a reduction below the Booked count is refused
outright rather than allowed to ride.

---

# Q4 — Deliberate denormalisation

1. **`bookings.status`, `cancelled_at`, `settled_at`** — a projection of `booking_events`. The log is
   authoritative for history; these columns let goals 6 and 8 filter, sort and aggregate without replaying
   it. The one I would call structural: it keeps the audit log honest *and* the list queries fast.
2. **`sessions.ends_at`** — derived, trigger-maintained, so the exclusion constraints and overlap queries
   operate on a real indexed value.
3. **`sessions.duration_min` / `capacity`** — copied from the class, because the brief requires
   per-session overrides and a later class edit must not rewrite history.
4. **Explicitly rejected: a `sessions.booked_count` counter.** Exactly the value that drifts under
   concurrency. The count is computed under the row lock instead.

**How the counts are served, and the trap in the word "booked".** No counter means every occupancy
figure is computed, and computing it one session at a time is an N+1 at its worst on the timetable. So the
aggregate takes a list — `SELECT session_id, status, count(*) … WHERE session_id IN (…) GROUP BY …` — one
statement per page, with the single-session call routed through the same function so there is one
definition rather than two that drift.

And a screen needs **three** of those numbers. `booked_count` counts bookings *currently* Booked, which is
right for a capacity decision and **zero once a class is settled** — so a screen drawing occupancy from it
alone shows a finished, fully attended class as an empty room. That is what happened, and it survived every
backend test, because no backend test asks what a *screen* should show. The payload carries
`attended_count` and `no_show_count` too, and one helper adds the three. Same aggregate, nothing stored.

---

# Q5 — What breaks first at 100x

In the order I expect them to hurt.

| What | Why it hurts | What replaces it |
|---|---|---|
| `count(*) OVER ` on the bookings list | Materialises the whole filtered set on every page | Cached/estimated total, or "1,000+ matches" past a threshold |
| `LIMIT`/`OFFSET` pagination | Deep offsets scan and discard | Keyset pagination — which also removes the window count |
| **Per-request round trips** | Deployment made this the dominant cost, not a theory: a trivial request spent 100 ms on its query and 475 ms on transaction overhead | Already five → three (Decision 9). Then fewer statements per request — the schema is not the bottleneck, the conversation is |
| Dashboard aggregations over `bookings` | Scanned on every load | Materialised view or scheduled rollup |
| A popular session as a `FOR UPDATE` hotspot | Lock held ~8–10 ms, so one session sustains ~100–125 bookings/sec. Sessions are independent, so this scales *with* the timetable | A reservation layer, for the flash-sale class only (Decision 2) |
| `pg_trgm` search | Fine to mid-size | Postgres full-text search, then a dedicated service |
| `booking_events` unbounded growth | The one table that can never be rewritten | Partition by month, archive cold partitions. No archival story today |
| The waitlist-position subquery | One correlated count per waitlisted row | A window function over a materialised per-session ranking |
| One instance serving writes and analytics | Contention between the two | A read replica for dashboards and lists |
| Connection pool ceiling | Supabase free tier | A paid tier, or a pooler tuned for it |
| The single-timezone assumption | A second studio breaks every `timestamptz` converted from local wall-clock time | A real migration, done deliberately rather than pretended-for |
| Backups | Free-tier Supabase has no point-in-time recovery | A paid tier, or scheduled logical dumps |

---

# The heaviest query (goal 6)

Text search over name and email, filters for class, session and status, a date range, three sorts, paging,
and the total number of matches — all server-side, in one statement.

```sql
SELECT b.id, b.status, b.booked_at,
       m.full_name, m.email,
       s.starts_at, s.id AS session_id,
       c.title AS class_title, c.discipline,
       count(*) OVER  AS total_matches          -- total for the whole filtered set
FROM bookings b
JOIN members  m ON m.id = b.member_id
JOIN sessions s ON s.id = b.session_id
JOIN classes  c ON c.id = s.class_id
WHERE s.deleted_at IS NULL
  AND (:status     IS NULL OR b.status     = :status)
  AND (:session_id IS NULL OR b.session_id = :session_id)
  AND (:class_id   IS NULL OR s.class_id   = :class_id)
  AND (:date_from  IS NULL OR s.starts_at >= :date_from_utc)   -- whole studio-local days
  AND (:date_to    IS NULL OR s.starts_at <  :date_to_utc)
  AND (:q IS NULL OR m.full_name   ILIKE '%' || :q || '%'
                  OR m.email::text ILIKE '%' || :q || '%')
  AND ( :is_staff                                  -- visible_sessions_clause, composed in
        OR s.primary_instructor_id = :viewer_id
        OR s.id IN (SELECT ci.session_id FROM session_co_instructors ci
                    WHERE ci.user_id = :viewer_id) )
ORDER BY  -- one of b.booked_at, b.status, s.starts_at — each with b.id as a stable tiebreak
LIMIT :limit OFFSET :offset;
```

- **`count(*) OVER ` rather than a second `COUNT`.** One round trip, and count and rows come from the
  same snapshot, so the total cannot disagree with the page beside it. Cost: materialising the filtered
  set — Q5 says what replaces it.
- **Every sort carries `b.id` as a tiebreak.** Without it two rows with identical `booked_at` swap places
  between pages and one is silently skipped or shown twice. Sorting by session is the one sort no index on
  `bookings` can serve, so `ix_sessions_starts_at` exists for it.
- **The search term is capped at 100 characters** — a long term shares few trigrams with anything, the
  index stops helping, and the query degrades to a sequential scan.
- **The date range is over class dates, compared as instants** rather than casting `starts_at` to a date.
  A cast is per-row, cannot use the index, and buckets by **UTC** — filing a 00:30 Kolkata class under the
  previous day. Bounds are built in studio time, local midnight to local midnight with a strict `<`.

