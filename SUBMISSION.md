# Submission

## Links

- **GitHub repository:** https://github.com/UjjWaL-0911/Class-Booking-System
- **Live application:** https://class-booking-system-55zn.onrender.com

| | |
|---|---|
| **Ten goals** | all done |
| **Stretch ideas** | five of the brief's nine built, four refused with reasons |
| **Deployed** | Render + Supabase (`ap-south-1`), seeded with a working studio |
| **Tests** | 415 backend, against real PostgreSQL — never SQLite |
| **History** | 61 commits across ten working sessions, written up in `docs/plan.md` |

**Sign in with any of these. The password is the same for all of them:**

| Role | Email | Password |
|------|-------|----------|
| Studio staff | `manager@studio.demo` | `StudioDemo!2026` |
| Instructor | `aryan@studio.demo` | `StudioDemo!2026` |
| Member — can book | `ananya.iyer@example.com` | `StudioDemo!2026` |
| Member — membership lapsed | `chirag.patel@example.com` | `StudioDemo!2026` |

**If you read one thing, read `docs/decisions.md`** — nine decisions, each the reason a layer, a table
or a whole absence exists. Six I later reversed, and those are the entries worth your time: two were
found only by deploying the software. Decisions 2 and 5 are the ones I would defend in an interview,
and the deferred capacity trigger in `schema.md` is the piece of work I am most pleased with.

## Notes for the reviewer

**It should be warm**, but the free tier sleeps: Render after 15 minutes, Supabase after a week. An
UptimeRobot check hits `/health/ready` every five minutes — one monitor for both, because the request
that proves the database is reachable is also the one that resets its timer. A slow first load is the
tier waking, not a broken deployment.

**Three things worth ten minutes, in order.**

**1. The concurrency test, if you only look at code.** `backend/tests/test_concurrency.py` fires 20
simultaneous bookings at a 12-seat session against real Postgres and asserts exactly 12 booked, 8
waitlisted. Every one of those tests was also run **once with the `FOR UPDATE` removed, and watched to
fail** — a concurrency test that has never been seen to fail is a test you are trusting rather than
one you have checked.

**2. `manager@studio.demo`, then `aryan@studio.demo`, on the same two screens.** Goal 1's roles are
enforced as a composable `WHERE` clause in the query layer, not a check a handler might forget: an
instructor cannot read a session they have no part in because the SQL never selects the row. Same
build, same endpoints. On Reports the manager sees every instructor's pay; Aryan sees one row, his
own — scoped by an explicit `User.id == viewer` rather than the visibility clause, because that clause
would have handed him the row of a colleague whose session he *co-instructs*.

**3. `chirag.patel@example.com`.** A member whose membership has lapsed. His account works, he reads
the timetable and his own history, and booking is refused naming the date it ended — by a rule written
and tested months before members could sign in. That is the whole reason self-service needed no notion
of payment, and it is more convincing to see than to read.

**The demo data was seeded by driving the real services, not by inserting rows**, so every booking
obeyed the same capacity, expiry and audit rules a real one does and the seed doubles as a test of the
write paths. 112 sessions across 11 weeks and roughly 1,300 bookings — waitlisted members,
cancellations that promoted somebody off the list, settled attendance, memberships in every expiry
state.

The API is deployed separately at `https://class-booking-system-backend.onrender.com`, but that is not
the link to open: the static site rewrites `/api/*` to it so the browser only ever sees one origin.

## Demo credentials

Every account uses the same password: **`StudioDemo!2026`**

| Role | Email | Password |
|------|-------|----------|
| Studio staff | `manager@studio.demo` | `StudioDemo!2026` |
| Instructor | `aryan@studio.demo` | `StudioDemo!2026` |
| Instructor | `marcus@studio.demo` | `StudioDemo!2026` |
| Instructor | `elena@studio.demo` | `StudioDemo!2026` |
| Member — can book | `ananya.iyer@example.com` | `StudioDemo!2026` |
| Member — membership lapsed | `chirag.patel@example.com` | `StudioDemo!2026` |


**There is no sign-up page, and only staff can add a member.** A member account implies a membership,
a membership implies somebody paid, and an endpoint on the open internet cannot know that. Staff
switch a login on instead, one member at a time. Decision 5 — and the first item under "what next",
because the refusal is correct and the resulting gap is not.

## Stack

| Layer | What I used | Why |
|-------|---------------|-----|
| Frontend | React 19, Vite 6, TypeScript (strict), Tailwind v4, TanStack Query v5, React Router v7, Radix for dialogs and popovers only | Almost all state here is server state, so a data-fetching layer earns its place and a client state manager does not. Radix is kept for the two places where being wrong is an accessibility bug rather than a matter of taste |
| Backend | FastAPI, SQLAlchemy 2.0 (async), asyncpg, Pydantic v2, Alembic on psycopg 3 | The booking rules need real transactions and row locks. Alembic runs on a *sync* driver deliberately: asyncpg refuses the multi-statement PL/pgSQL bodies these migrations are full of |
| Database | PostgreSQL 17.6 on Supabase (`ap-south-1`) | The correctness guarantees are Postgres features rather than application code: `SELECT … FOR UPDATE`, GiST exclusion constraints, partial unique indexes, and triggers that make the audit table refuse `UPDATE`, `DELETE` and `TRUNCATE` |
| Hosting | Render — a Web Service for the API, a Static Site for the SPA, `/api/*` rewritten to the API | One origin keeps the refresh cookie first-party `SameSite=Lax` and leaves no CORS policy to misconfigure. Two origins would need `SameSite=None` and a permissive policy — strictly worse security for no gain |

## Goal checklist


| # | Goal | Status | Notes |
|---|------|--------|-------|
| 1 | Accounts and roles | Done | argon2id, in-memory access token with a rotating httpOnly refresh cookie. Roles enforced as a composable `WHERE` clause, so the row is never selected rather than filtered afterwards. A third role arriving later made every `if staff … else instructor` reachable by somebody it was not written for — 18 of them, all revisited (Decision 3) |
| 2 | Classes | Done | Archiving is a timestamp, not a delete: sessions and history survive, new bookings are refused. Titles are unique among live classes, case-insensitively, as a partial index on `lower(title)` |
| 3 | Sessions inside classes | Done | A room or an instructor being double-booked is refused by a **GiST exclusion constraint**, not by a service check — so no future code path can reintroduce it |
| 4 | A booking lifecycle with rules | Done | Capacity decided under `SELECT … FOR UPDATE` on the *session* row, with `lock_timeout = 3s`. 20 simultaneous bookings for 12 seats produce exactly 12 — a test runs that race for real against Postgres. Cancelling promotes in the same transaction: there is no code path where a seat frees and the waitlist is not considered |
| 5 | Co-instructors | Done | One primary, any number of others. A co-instructor may settle the register and is deliberately **not** paid by the payroll report — paying two people a full rate for one class is a policy decision this system should not make for a studio |
| 6 | Finding bookings | Done | `pg_trgm` search over name and email, filters, four sorts, paging with the total across the whole filtered set. The trigram index needed a `::text` cast in the *query* — on `citext` it builds happily and is then never used, which measurement caught and reading did not |
| 7 | Generating a recurring schedule | Done | A `SAVEPOINT` per candidate, so one clash skips one session instead of aborting forty, and a report naming every skip. Bounded at 200 because Postgres caches 64 subtransaction ids per backend before a performance cliff |
| 8 | A dashboard | Done | Four headline numbers, two breakdowns and eight weeks of attendance in **one** statement. Measured *slower* locally (4.5 ms against 3.6 ms for six queries) and faster once the database is a network away — written up honestly rather than quoting the number that flatters it |
| 9 | History you cannot rewrite | Done | Append-only `booking_events`, enforced by triggers that raise on `UPDATE`, `DELETE` and `TRUNCATE`. Not a convention — I cannot rewrite it either, and the test suite had to be restructured around not being able to truncate it |
| 10 | Expiring membership alerts | Done | Dismissals are keyed on the expiry *as it was when dismissed*, so renewing a membership brings the alert back by itself. No flag, no background job — the re-trigger falls out of the key |

**Beyond the ten goals**, six things are built, each recorded as a deliberate addition rather than
folded in quietly: staff creating accounts — goals 3, 5 and 7 take an instructor *by id* and nothing
else could produce one — plus **five of the brief's nine stretch ideas**: a public timetable, booking
a whole term in one action, room utilisation, instructor payroll, waitlist position, and self-service
booking for members.

Of the four remaining: **substitute swaps are half-built** — reassigning a session's instructor works
today, and the "advance notice" half does not, because nothing notifies anyone; **reminders** need a scheduler and a mail provider and reverse Decision 7; **credit
pricing** would rewrite the booking gate, which is the best-tested code here; and **public member
sign-up** is refused on the grounds above rather than deferred.

## How much time did I actually spend?

**About 16–18 hours**, against the brief's 12.

The overrun has one cause I would repeat and one I would not. **Two independent review rounds of my
own work cost more than several of the goals did** — the first found twelve real issues, the second
found eight *new* ones introduced by the first round's fixes. That is the part I would spend again.
The part I would not: I rebuilt the visual layer more often than the work justified, and `plan.md`
records it — the frontend's *visual* passes took ~30% against ~10% expected, while the screens
themselves came in at ~30% against ~50%.

What the repository shows on its own: **61 commits** across **ten working sessions**, written up in
`docs/plan.md` with estimated-versus-actual for each.

## What would I do next, with another 12 hours?

In the order I would actually do them.

**1. A way for a member to get an account without ringing the desk (3–4 hours).** The first thing I
would build, and it is a product gap rather than a technical one. Today **only staff can add a
member, and only staff can switch on their login** — so somebody who finds the site cannot become a
customer. I refused public sign-up deliberately (Decision 5: an account implies a membership implies
payment), and I still think the refusal is right; the *gap it leaves* is not.

The honest shape is a **lead capture rather than a sign-up**: anyone can register, which creates a
member record with **no valid membership** and an account that can sign in, read the timetable and
book nothing. The desk sees a queue of new registrations and sets an expiry when the person pays.
That needs no payment integration and changes no booking rule — goal 4's expiry check already refuses
them, which is the same property that let self-service ship without touching payment. Most of the
work is the unglamorous half: a rate limit on an unauthenticated write endpoint, and a duplicate-email
policy that refuses rather than lets a stranger claim an existing member's booking history.

**2. Password change and reset (2 hours).** Nobody can change a password — not staff, not
instructors, not members. Accounts are created with one and handed over in conversation. Thin but
defensible while five colleagues had logins; giving customers accounts made it a real problem.
Change-your-own is an hour; reset needs the mail sender item 1 also wants, which is why they belong
in one block of work.

**3. Frontend tests (4 hours).** The backend has 415; the interface has a typechecker, a linter, a
build and a person clicking through. I would not spread them thin — the booking dialog and the
session roster hold essentially all the client-side logic worth protecting, and the rest is assembly
over server state the API tests already cover.

**4. CI (1 hour).** Everything runs green locally on every change and nothing enforces it on push.

**Where I would go at 100× the data**, because the answer is not "more tests":

- **The `FOR UPDATE` hotspot is the real ceiling.** Cancel-and-promote is eight statements, so the
  lock is held ~8–10 ms and one session sustains roughly 100–125 bookings/second. Sessions are
  independent, so this scales *with* the timetable rather than against it — but a single flash-sale
  class is capped, and that is where a reservation layer (Decision 2) starts earning its keep rather
  than being architecture astronomy.
- **Round trips, not queries, are the latency budget.** Profiling production showed a trivial request
  spending 100 ms on its query and 475 ms on overhead — a connection ping and two `SET LOCAL`
  statements — paid identically whether the endpoint returned 193 bytes or a whole dashboard. Merging
  the timeouts into one `set_config` call and dropping `pool_pre_ping` took a measured request from
  694 ms to 339 ms. At scale the next move is fewer statements per request, not faster ones.
- **`booking_events` grows without bound** and is the one table that can never be rewritten. Partition
  by month before it matters, archive cold partitions, never delete.
- **The dashboard aggregates over `bookings` on every load.** One statement is right at this size; at
  100× it is a materialised view or a scheduled rollup. The honest trigger is when that query stops
  fitting inside the page's latency budget, not when it starts to "feel slow".
- **Login rate limiting is per-instance** — correct at one, wrong at two, and the only piece of the
  design that does not survive the horizontal scaling the rest is built for. It moves to Redis the
  same day a second instance does.

## What am I least happy with in this codebase, and why?

**The interface has no automated tests.** Everything above is a gap I can name and schedule; this is
the one I would flag in a review of somebody else's work. The call was deliberate — the booking rules
are where being wrong costs a studio money, so the budget went to the backend and the concurrency
suite, but "deliberate" and "comfortable" are different words.

**Nobody can change their own password.** There is no mail sender, so an invitation or a reset link
has nothing to travel on. Thin but honest while only colleagues had logins; giving members accounts
made it worse without fixing it.

**Session rates have no history.** Change what an instructor is paid today and last month's payroll
total changes with it, because the report multiplies sessions by the rate as it stands *now*. Correct
and free for a studio that revisits rates yearly; wrong the first time somebody gets a raise
mid-month. The dialog says so where somebody is about to do it, but the honest fix is a rates table
with effective dates. Listed under "Decisions still open".

**One function matches on error-message text.** The term-booking report maps a rule's own sentence
onto a machine-readable reason by looking for words in it. Confined to one small greppable function,
and still wrong — every `RuleViolation` should carry a code. A wider change than the feature that
needed it should have made alone.

**The dashboard duplicates the visibility rule**, written out literally in SQL rather than composed
in, because composing a SQLAlchemy clause into a `text` statement means building SQL by string
concatenation — the one habit I did not want in a file that also holds a large literal query. The
duplicate is covered by a test asserting the two agree, which is a mitigation rather than a fix.
Decision 3.

**And the deployment describes itself nowhere.** It works and it is verified, but it lives in two
Render dashboards rather than in this repository. Every other decision here is readable in the code;
that one is not.
