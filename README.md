# Class Booking System

A back-office booking system for a studio running a weekly slate of classes across a few rooms and
several instructors. It replaces the sign-up sheet taped to the door and the membership binder at the
front desk: staff schedule sessions and manage members, instructors see their own sessions and record
who showed up, and a cancellation pulls the next person off the waiting list automatically.

**Live:** https://class-booking-system-55zn.onrender.com

Sign in with any of these — the password is the same for all of them:

| Role | Email | Password |
|------|-------|----------|
| Studio staff | `manager@studio.demo` | `StudioDemo!2026` |
| Instructor | `aryan@studio.demo` | `StudioDemo!2026` |
| Member (can book) | `ananya.iyer@example.com` | `StudioDemo!2026` |
| Member (membership lapsed) | `chirag.patel@example.com` | `StudioDemo!2026` |

The free tier sleeps after 15 minutes of inactivity, so a first load can take a minute to wake. A
public timetable is readable without signing in at `/schedule`.

## Stack

| | |
|---|---|
| **API** | FastAPI, SQLAlchemy 2.0 async, asyncpg, Pydantic v2, Python 3.11 |
| **Database** | PostgreSQL 17, Alembic migrations (on psycopg 3 — DDL and the async driver do not mix) |
| **Web** | React 19, TypeScript strict, Vite 6, Tailwind v4, TanStack Query v5, React Router v7 |
| **Auth** | JWT access token in memory, refresh token in a first-party cookie, argon2id hashing |
| **Hosting** | Render (API + static site), Supabase (`ap-south-1`) |

Correctness lives in the database wherever it can: GiST exclusion constraints stop an instructor or a
room being double-booked, a deferred constraint trigger enforces session capacity, and
`booking_events` is append-only — its triggers reject UPDATE, DELETE and TRUNCATE, including from
staff. Concurrent bookings for the last place are serialised by `SELECT … FOR UPDATE` on the session
row.

## Running it locally

**Prerequisites:** Python 3.11+, Node 20+, and a PostgreSQL 17 server you can create databases on.

### 1. Database

```bash
createdb class_booking
createdb class_booking_test        # only needed to run the test suite
```

### 2. API

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

cp .env.example .env               # then edit it — see below
alembic upgrade head
python -m app.seed                 # demo studio: 112 sessions, ~1,300 bookings
uvicorn app.main:app --reload      # http://127.0.0.1:8000
```

`.env` needs four values filled in; the rest of the file documents itself.

| Variable | Notes |
|---|---|
| `DATABASE_URL` | The application connection — `postgresql+asyncpg://…` |
| `MIGRATION_DATABASE_URL` | Alembic only, no `+asyncpg` — migrations run on psycopg 3 |
| `JWT_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `STUDIO_TIMEZONE` | **Required, no default.** Four of the ten goals count by the studio's day rather than UTC, so a wrong guess here produces wrong numbers rather than a crash |

`python -m app.seed --reset` drops the schema, re-migrates and re-seeds. That is the only way back to
a clean slate, because `booking_events` refuses both DELETE and TRUNCATE by design.

The seed drives the real services rather than inserting rows, so every booking it creates obeyed the
same capacity, expiry and audit rules a real one does.

### 3. Web

```bash
cd frontend
npm install
npm run dev                        # http://localhost:5173
```

The dev server proxies `/api` to `127.0.0.1:8000` (override with `VITE_API_TARGET`). The app never
calls an absolute API URL — the refresh cookie is first-party and `/auth/refresh` verifies the
request's `Origin`, so talking to a second origin in development would mean the cookie silently never
arrives. Production does the same rewrite at the static host.

## Tests

```bash
cd backend
export TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/class_booking_test
pytest                             # 415 tests
```

They run against real PostgreSQL, never SQLite — exclusion constraints, deferrable constraint
triggers and `tstzrange` have no SQLite equivalent, and they are most of what makes this system worth
testing. `backend/tests/test_concurrency.py` fires simultaneous bookings at a full session from
separate connections; every one of those tests was also run once with the `FOR UPDATE` removed and
watched to fail.

Checks:

```bash
cd backend  && ruff check . && mypy app                 # lint, types
cd frontend && npm run typecheck && npm run lint        # tsc --noEmit, eslint
```

## Layout

```
backend/
  app/
    api/v1/routers/   HTTP layer — one router per resource
    services/         business rules, transaction boundaries, the session lock
    repositories/     queries, including the composable visibility clauses
    models/           SQLAlchemy models
    schemas/          Pydantic request and response models
    core/             settings, auth, dependencies, error translation
    db/               engine, session factory, transaction guards
    seed/             the demo studio
  alembic/versions/   five migrations
  tests/              415 tests
frontend/
  src/
    routes/           one file per screen
    components/       ui/ primitives, domain/ studio-specific
    api/              client, endpoints, response models
    hooks/            TanStack Query wrappers
docs/                 architecture, schema, plan, decisions, ai-prompts
```

Authorization is a `WHERE` clause composed into the query rather than a check after it — an
instructor cannot read a session they have no part in because the SQL never selects the row. There is
one build for every role; the server scopes what each one sees.

## Documentation

| File | What it covers |
|------|----------------|
| [`docs/decisions.md`](docs/decisions.md) | Nine decisions that shaped the codebase, six of them later reversed. **Read this one first.** |
| [`docs/architecture.md`](docs/architecture.md) | The moving pieces, where each runs, and one request end to end |
| [`docs/schema.md`](docs/schema.md) | Tables, relationships, which constraints live in the database, and what breaks first at 100× |
| [`docs/plan.md`](docs/plan.md) | How the work was split, the order it was built in, estimates versus actuals |
| [`docs/ai-prompts.md`](docs/ai-prompts.md) | The prompts used, grouped by intent, including the ones that produced something wrong |
| [`SUBMISSION.md`](SUBMISSION.md) | Submission notes: goal-by-goal status, what was left out, and why |

## The ten goals

The brief this was built against is kept verbatim in [`ASSIGNMENT.md`](ASSIGNMENT.md). Its ten
requirements, and where each one lives:

| | Goal | Where |
|---|------|-------|
| 1 | Accounts and roles, enforced on the server | `repositories/visibility.py`, `core/deps.py` |
| 2 | Classes, editable and archivable | `services/class_service.py` |
| 3 | Sessions inside classes, with a room and instructor | `services/session_service.py` |
| 4 | The booking lifecycle, capacity, waiting list, expiry | `services/booking_service.py` |
| 5 | Co-instructors | `models/class_session.py` |
| 6 | Finding bookings — search, filters, sorting, paging | `repositories/booking_search.py` |
| 7 | Generating a recurring schedule; CSV export | `services/recurrence_service.py` |
| 8 | The dashboard | `repositories/dashboard.py` |
| 9 | History that cannot be rewritten | the `booking_events` triggers |
| 10 | Expiring membership alerts | `services/alert_service.py` |

Six things beyond the ten are built, each recorded as a deliberate addition rather than folded in
quietly: staff creating accounts, plus five of the brief's stretch ideas — a public timetable, booking
a whole term in one action, room utilisation and instructor payroll, waitlist position, and
self-service booking for members. What was deliberately left out, and why, is in `SUBMISSION.md`.
