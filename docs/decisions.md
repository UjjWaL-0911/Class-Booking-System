# Decisions

Log the decisions that actually shaped this codebase — the ones where a real alternative existed and
you picked one. At least five entries. For each: what you chose, what you rejected, and why. At least
one entry must be a decision you later reversed — say what changed your mind. It can be any entry
below, not necessarily the last one; add a **Later reversed:** line to whichever one it is.

---

Nine decisions. Each one determined the *shape* of something — a layer, a table, a whole absence —
rather than a detail inside it. I made perhaps forty choices worth arguing about; these are the ones
where picking the other option would have produced a different codebase rather than a different file.

**Six of them I later reversed**, marked ↩, and those are the entries worth reading first: they are
where the design met something it had not accounted for. Two were found only by deploying the
software, which is the most useful thing this project taught me.

The implementation detail sits where it belongs — `schema.md` for the tables, `architecture.md` for
the request path, the module docstrings for the code. This file is the map.

---

## 1 — Correctness belongs to the database, not to my Python

**Chose:** every rule that must hold whatever code runs is a constraint, an index or a trigger.
Exclusion constraints refuse a double-booked room; a partial unique index refuses a member holding two
places on one session; triggers make the audit log reject `UPDATE`, `DELETE` **and** `TRUNCATE`.

**Rejected:** enforcing these in the service layer, where they would be correct until the first code
path that forgot to call the check.

**Why:** a migration, a script and a developer at a `psql` prompt all hit a constraint equally. A rule
living in one service is one forgotten call site from being false. The test I applied throughout: *would
this still need to be true if the application were replaced tomorrow?* If yes, it goes in Postgres. If it
needs a row count or a sentence explaining itself — "this membership expired on 12 August" — it stays in
the application, because a `CHECK` cannot say that.

**The detail worth one paragraph**, because it nearly went wrong: the capacity backstop is a *deferred*
trigger, and the obvious implementation is a lie. A deferred trigger that merely runs `count(*)` at
commit executes inside the committing transaction under `READ COMMITTED`, so two transactions that both
skipped the row lock each count, each pass, and both commit. It would catch a single-threaded bug while
*reading* like a concurrency guarantee. So the trigger takes `FOR UPDATE` itself.

---

## 2 — Postgres row locks are the entire concurrency control ↩

**Chose:** `SELECT … FOR UPDATE` on the *session* row, with `lock_timeout = 3s`. Nothing else.

**Rejected:** Redis locks, a job queue, a seat-hold/reservation system, and `SERIALIZABLE` isolation.

**Why:** all contention in this system is one question — is there a seat left — and it is per-session.
Locking the parent gives every contender for that session one queue while different sessions never
block each other, so throughput scales *with* the timetable. Twenty simultaneous bookings for twelve
seats produce exactly twelve, and there is a test that runs that race against real Postgres.

**Later reversed — this entry is the reversal.** My first design was a "RedBus / BookMyShow"
architecture: seat holds, Redis, pub/sub, WebSockets. It was a good architecture for a different
problem. Re-reading the brief against it showed goal 4 books **directly** to Booked or Waitlisted —
there is no deliberation window for a hold to protect, and no goal asks one person's screen to change
because of another's action. I had framed my own question around a solution and named two systems whose
scale is nothing like a studio where classes fill over days.

**The ceiling is written down rather than engineered away.** Cancel-and-promote is eight statements, so
the lock is held ~8–10 ms and one session sustains 100–125 bookings/second. If a single class ever
needs more, the escalation order is recorded — and the design for it is a Postgres `holds` table, not a
new piece of infrastructure.

---

## 3 — Authorization is a filter composed into the query, never a check after it ↩

**Chose:** one function returning a SQL clause, composed into every session and booking query.
An instructor cannot read a session they have no part in because **the row is never selected**.

**Rejected:** fetching rows and filtering them in the handler, or a permission check per endpoint.

**Why:** a forgotten filter returns *nothing*, which is noticed within a minute. A forgotten check
leaks, and is noticed by whoever it leaked to. The member directory is then defined *in terms of* the
session clause rather than repeating it, so the roster and the directory can never disagree about who
exists.

**Later reversed:** the directory first granted instructors the whole binder, reasoning that "a roster
is names". The flaw is that a roster is the names in *your* class, while the endpoint served every
member the studio ever had, each with an expiry beside them.

**And reversed again when a third role arrived.** Every check was written as `if staff … else
instructor`; adding `member` made each `else` reachable by somebody it was not written for. There were
eighteen. They failed *closed* — a member matches no instructor row, so filters return nothing — which
made the work safe rather than harmless. The one that mattered was the instructor picker: that list
feeds every "who is teaching this" dropdown **and** the server validates against the same rule, so a
member appearing there would not merely have been offered as somebody who could teach a class — it
would have been accepted.

---

## 4 — Every audience gets a response model of its own ↩

**Chose:** separate, near-duplicate output models per audience — the public timetable, the member's own
view, the staff list — each written from scratch.

**Rejected:** one model per table, filtered per caller.

**Why:** filtering a shared shape means every field added to it later reaches the wrong audience unless
somebody remembers to filter that one too — and the remembering happens in a different file from the
adding. **A model that never had the field cannot leak it**, which is the same reason `password_hash`
does not exist on the user output model rather than being excluded from it. Tests assert the exact key
set, so widening one of these fails a test rather than discloses quietly.

It has already caught two things. A pay rate was added to the wrong model, and the sign-in response's
key-set test failed immediately.

**Later reversed:** the public timetable's 200-session cap **truncated in silence** while the response
still claimed the full window. A test caught it, because the accumulated test database overflows 200.
The response now carries `truncated`. A limit that lies about what it returned is worse than a shorter
limit.

---

## 5 — Members are records, not accounts — and there is no sign-up page ↩

**Chose:** members are customer records with no login. Staff book on their behalf. Later, staff may
switch on a login for one member at a time; there is still no public registration for anybody.

**Rejected:** member logins from the start, and — when self-service was eventually built — a public
sign-up page.

**Why members are records:** the brief describes bookings created by staff. Accounts would have added a
third role, registration, password reset and a much larger authorisation surface in service of a stretch
idea. The decision that actually mattered was making it **cheap to reverse** — `members` is a separate
table from `users`, so adding logins later moved no existing row.

**Why there is still no sign-up page:** **a member
account implies a membership, a membership implies somebody paid, and an endpoint open to the internet
cannot know that.** Sign-up therefore has two possible behaviours and both are wrong — it grants a
membership nobody agreed to, or it creates accounts that can book nothing until the desk intervenes
anyway. Making the first safe means building payment, or a pending-member lifecycle with its own screens
and rules: a *product* decision a studio makes, not one a booking system assumes on their behalf.
Letting a stranger *claim* an existing record would be worse — with no mail sender, nothing proves they
own the address, and the record carries somebody's booking history.

**What that buys:** payment never enters the feature at all. Switching on a login does not touch the
membership expiry, so whether somebody may book is still the rule written and tested months earlier. A
lapsed member signs in, reads their history, and is refused at the point of booking with the date it
ended. **What it costs:** a new customer cannot onboard themselves. They ring the desk — which is how
booking already works here.

**Later reversed — the prediction about where the credential lives.** This decision originally said the
self-service phase would add a password to `members`. It cannot: every write names its actor as a
foreign key into `users`, so a member booking their own place has nothing valid to record as the
creator. Fixing that from the `members` side means teaching the **append-only** timeline about two
species of actor — the one table in this schema that can never be revised. The credential lives on
`users` instead, joined by a nullable column. It paid a dividend I had not predicted: the audit log now
distinguishes "the member booked themselves" from "the desk booked them" for free.

---

## 6 — Build the ten goals exactly, and delete what exceeds them ↩

**Chose:** the brief is the specification. Anything built that no goal asks for gets removed, however
well it works.

**Rejected:** keeping working code because it works.

**Why:** every extra component is a thing to deploy, monitor, explain and get wrong. The clearest case
is the one I reversed: **a least-privilege database role was built, applied, and then deleted.** It
worked. It went because the audit-log triggers already satisfy the goal on their own, and the role added
a second credential and real deployment risk for defence-in-depth behind a guarantee that already held.

The same discipline is why the five stretch ideas that *were* built are each recorded as deliberate
additions rather than folded in quietly — and why four others were refused with reasons rather than
deferred with an apology.

---

## 7 — Everything runs inside one request, on one origin

**Chose:** no background workers, no queue, no cache, no realtime layer. One web service, one database,
one static site — with the static host rewriting `/api/*` to the API so the browser sees a single
origin.

**Rejected:** BullMQ and then Arq for jobs; Redis for locks, caching and rate limiting; two origins with
CORS.

**Why:** nothing in the ten goals is long-running, so a queue would have been a second runtime to deploy
and monitor for zero jobs. And the single origin is not a convenience — it keeps the refresh cookie
first-party `SameSite=Lax` and leaves no CORS policy to misconfigure, where two origins would require
loosening both for no gain. It is verified rather than assumed: a session was rotated through the static
host using only the cookie.

The honest consequence is named rather than hidden: **the login rate limiter is in-process**, which is
correct at one instance and wrong at two. It is the only piece of the design that does not survive the
horizontal scaling the rest is built for.

---

## 8 — The client holds no state the server owns

**Chose:** a data-fetching layer and nothing else. Server state is cached and invalidated; the only
client state is what is in a form right now.

**Rejected:** Redux, Zustand, a context tree — and a component library.

**Why:** almost everything on these screens *is* server state, so a client store would have been a
second copy of the truth with its own staleness rules. The same logic governs the rules themselves: when
the interface wanted something the server did not return, the **endpoint** changed rather than the
client assembling it from two calls. Six times. A rule that lives in the browser is a rule that can
disagree with the server about whether a class is full.

The one exception is deliberate: a component library is used for dialogs and popovers only, where focus
trapping being wrong is an accessibility bug rather than a matter of taste.

---

## 9 — Measure rather than reason, and record reversals rather than edit them ↩

**Chose:** run the thing, profile it, and when I was wrong, append the correction rather than quietly
fixing the sentence.

**Rejected:** trusting that code which reads correctly *is* correct.

**Why:** this is the methodology that produced more corrections than review did, and four of them were
invisible until the software was real:

- A trigram index on a case-insensitive column **builds happily and is then never used** — the planner
  will not use it for that operator. An index that exists, reports as valid, and does nothing.
- The dashboard's single-query design measured *slower* locally than six simple queries — 4.5 ms against
  3.6 ms — and faster once the database was a network away. I wrote down the number that did not flatter
  the decision.
- Every paginated list kept its previous page while loading. At 3 ms that is polish; at 300 ms the
  header says one week while the rows describe another. **No test would have caught it** — the data was
  always correct, and only latency made the inconsistency visible.
- Most of a request was not the query: 100 ms of query against 475 ms of fixed overhead, paid
  identically whether an endpoint returned 193 bytes or a full dashboard. Removing two round trips took
  a measured request from 694 ms to 339 ms.

**Later reversed, and this is the one I am least comfortable with:** the API was deployed to a region
three hundred milliseconds from its database, while `architecture.md` already contained the sentence
*"regions are pinned"* and the reason for it. **I had written the rule and then not checked I had
followed it.** Moving the service cut a page load from 6.5 seconds to 1.6 with no code change at all.

---

## Decisions still open

The ones I expect to revisit first. Several are open *because* the code exists, not despite it.

- **Whether members should ever sign themselves up.** Decision 5 says not without a membership
  lifecycle. The honest first step is a lead capture — a record with no membership, and a queue for the
  desk — which is a different feature, and one the studio should ask for rather than receive.
- **Whether anyone can change their own password.** Nobody can, staff included. There is no mail sender,
  so a reset link has nothing to travel on.
- **Whether a pay rate should carry its own history.** It is undated today, so a raise rewrites what last
  month's payroll report says. Right for rates that move yearly; wrong the first time somebody needs the
  old figure back.
- **Whether the dashboard should keep its own copy of the visibility rule.** It is the one place that
  rule is duplicated, written literally in SQL because composing a clause into a raw statement means
  building SQL by string concatenation. Covered by a test asserting the two agree.
- **Whether the client should keep its own copy of the validation rules.** The compromise in place — the
  server constraint quoted beside each client rule — is a convention, and conventions are only as good
  as the next person's attention.
- **Whether account creation should have stopped where it did.** Staff can add a colleague; nothing
  edits, deactivates or resets one. Deactivation is the next endpoint I would add.
- **Whether co-instructors should be paid.** Payroll pays only the primary instructor, which is a
  defensible default and not a policy anybody has actually chosen.
- **Whether the deployment should describe itself.** It lives in two dashboards rather than a
  `render.yaml`. Every other decision here is readable in the repository; this one is not.
- **Whether the interface earns a test suite before anything else.** It has a typechecker, a linter, a
  build and a person clicking through. The biggest gap in the project.
