# Plan

I worked in **sessions**, and split every session into **components**. A session is one sitting aimed at a
single goal — settling the concurrency control, building the domain, getting the interface working. A
component is the smallest piece I can describe clearly, build, and prove before moving on.

That two-level split is the one planning decision I made up front, and I made it because of the shape of
this brief rather than out of habit. Most of these ten goals are ordinary CRUD. One of them, the booking
lifecycle, where capacity, a waitlist, an automatic promotion and an immutable audit trail all have to
stay consistent while two people act at once, is not. Work like that is not finished when it runs. It is
finished when you can show it holding under conditions you created on purpose. Sessions gave me somewhere
to think, components gave me somewhere to check.

What follows is the record of what actually happened, including the three places my order turned out to
be wrong. Deployment has now happened, and session 9 is written from what it did rather than what I
expected of it.

## How I broke the work up

Not by days. A day measures effort rather than progress: "I worked on bookings on Tuesday" does not say
whether bookings work. A component is usually one goal — sometimes two where they share an aggregate —
and it always ends in something demonstrable.

Every component went through the same five steps:

1. **Describe what it has to do**, reading what the brief actually says about it rather than what I
   remember it saying. Several of these goals hide their real requirement in a subordinate clause.
2. **Argue the design**, including the parts I disagreed with on the first pass.
3. **Build it.**
4. **Run the three-step check:** `ruff`, `mypy --strict`, then the tests.
5. **Verify the new behaviour against real PostgreSQL**, then move on.

Two rules held the whole thing together.

**Nothing was built before its design had been argued.** That is why the Redis reversal, the biggest
change of direction in this project happened while it was still a paragraph, rather than after a week
of code existed to defend. Reversing a paragraph costs an afternoon of thinking. Reversing a running
subsystem costs the thinking, plus the sunk cost, plus the temptation to keep it.

**Every component ended green.** I have never left the suite failing between components. That is worth
more than it sounds because when something breaks, it belongs to the thing I just wrote rather than to something
three components ago. It turns debugging from archaeology into reading the last diff.

The alternative, build the whole backend, then test it would have hidden most of the bugs listed
further down, and nearly all of those were caught by a test written minutes after the code it covers.

The interface kept the same loop with a weaker step 4: `tsc --noEmit`, `eslint --max-warnings 0`, a
production build, and walking the affected screen against the seeded database as both a manager and an
instructor.

## The sessions, and the components inside them

### Session 1 — Read the brief, and design before writing anything

| # | Component | Why here |
|---|---|---|
| 1 | Read the brief and choose the stack | Grouping the ten goals by risk is what identified the five that actually decide this submission |
| 2 | Concurrency design | The booking lock for self service booking  system  shapes the schema, so it had to come before it. This is where I designed a Redis architecture and then threw it away |
| 3 | `schema.md` | Every later component depends on the table shapes. Six open questions surfaced here and were answered instead of assumed here |
| 4 | `architecture.md`, then an independent review | Reviewed before any code existed, which is the cheapest possible moment to find out a design is wrong |
| 5 | `decisions.md` | Written while the reasoning was fresh. Reconstructing a decision three weeks later produces a justification, not a record |

I spent the first session not writing code, on purpose. The concurrency design is what the rest of the
system is shaped around, and getting it wrong would have meant rewriting the schema, the services and the
tests together.

### Session 2 — The floor everything else stands on

| # | Component | Why here |
|---|---|---|
| 6 | Skeleton and configuration | Nothing can be built on settings that fail quietly |
| 7 | **Local PostgreSQL, and verifying the platform claims** | Deliberately out of my intended order, see below |
| 8 | Database layer | Engine, pooler compatibility, transaction helpers |
| 9 | Models and migrations | The schema as code, with the triggers and constraints an ORM cannot express |

### Session 3 — The domain, in dependency order

| # | Component | Why here |
|---|---|---|
| 10 | Auth and roles (goal 1) | Every later endpoint needs a caller and a role |
| 11 | Classes (goal 2) | The simplest aggregate, and a good place to settle the router / service / schema layering once |
| 12 | Members | Not a goal on its own. It is the prerequisite that goals 4 and 10 are built on |
| 13 | Sessions and co-instructors (goals 3, 5) | Introduces the visibility filter that goals 4, 6 and 8 all reuse |
| 14 | **Booking lifecycle and timeline (goals 4, 9)** | The centrepiece. Everything before it exists so that this could be built properly |
| 15 | Concurrency tests | Immediately after, while the locking was still in my head and every case verified to fail with the lock removed |

Component 15 is the one I would defend hardest. A concurrency test that has never been seen to fail is
not a test, it is a decoration: it passes just as happily on a system with no locking at all. Every case
in that suite was run once with the `FOR UPDATE` taken out, watched to fail, and then put back.

### Session 4 — The reads the studio actually uses

| # | Component | Why here |
|---|---|---|
| 16 | Bookings list (goal 6) | Reads what goal 4 writes, and needs the visibility filter from component 13 |
| 17 | Recurring generator and CSV export (goal 7) | Needs sessions and bookings both |
| 18 | Dashboard and membership alerts (goals 8, 10) | Read-only aggregations over everything above |

These went faster than anything else in the project, and not because they are trivial. By this point the
layering was settled and the visibility rule lived in one place, so each of them was mostly a query and a
shape.

### Session 5 — Make it demonstrable, then audit what I had claimed

| # | Component | Why here |
|---|---|---|
| 19 | Seed data | Only meaningful once every write path exists, because it drives them rather than inserting rows |
| 20 | Structured logging, login rate limiting, lock-hold tests | Closing the gap between what my documents claimed and what the repository contained |

The audit at the end of this session was uncomfortable, and it is the most useful hour in the project. I
had every present-tense infrastructure claim in `architecture.md` checked against the file system, and
**six of them did not exist** — structured logging, the rate limiter, error reporting, a CI workflow, a
compose file, and a lock-hold test I had described in some detail. I built the small ones and marked the
rest honestly rather than deleting the sentences. A document that makes fifteen checkable claims invites
a reader to check one, and a single claim that turns out to be aspirational makes them reread the other
fourteen as research rather than experience.

### Session 6 — The interface

| # | Component | Why here |
|---|---|---|
| 21 | **Design direction, then a drawn canvas** | Four screens drawn and argued before a line of React. Judging a dense roster at 14px is far cheaper in a mockup than in components |
| 22 | Frontend foundation | Tokens, the fetch client, the query layer. Nothing visible, and every screen above it depends on the token refresh being single-flight |
| 23 | UI primitives, then the domain atoms | Occupancy marks, status chips, expiry chips, the session and member pickers. Built once, used everywhere |
| 24 | The screens | In goal order, so each one proved an endpoint end to end as it was built |
| 25 | **The three backend gaps the interface exposed** | Out of order and unavoidable — see below |
| 26 | Input validation across every form | Mirrored from the Pydantic constraints, with each limit named beside the rule so the duplication is visible rather than hidden |
| 27 | Landing page, theming, the visual passes | The most iterations and the fewest decisions of anything in this table |

### Session 7 — Hardening, from actually using it

This session was in no plan I would have written. It exists because once there was a working interface and
a database full of plausible data, I started using the thing as a person rather than testing it as its
author — and it kept giving up defects that nothing else had caught.

| Component | What using it found |
|---|---|
| Member directory scoping | An instructor could list **every** member in the studio, membership expiry included. Goal 1 scopes *sessions* rather than the directory, so this was not a breach of the letter of the brief. It was the wrong default, and it was undeclared, which is worse |
| Cancelling from the bookings list | Cancelling worked, and was reachable only from a session's roster. On the screen literally called Bookings there was no way to do it |
| The way into goal 9's timeline | It was there — as grey text with no underline, at the edge of a six-column table. Genuinely clickable, and it read as a label |
| Goal 3's last clause | "Opening a class shows its sessions." The server had accepted a `class_id` filter all along; nothing in the interface ever passed it |
| The seeded timelines | Four in eighteen ran **backwards** — a booking created on the 12th, cancelled on the 11th. The audit trail was honest about what happened and who did it; only the demo's clock was wrong. On the one screen a reviewer opens to check immutability, that is the worst place to have it |
| Adding people | Goals 3, 5 and 7 take an instructor *by id*, and nothing could bring an instructor into existence except the seed script. A studio that hired somebody had no way to say so |

None of those is exotic. Every one of them is the kind of thing a suite of the shape I wrote will never
catch, because each test asserts what I already believed.

### Session 8 — Past the ten goals

Only once the ten were genuinely complete, and each one recorded as an addition rather than folded in as
though it had been asked for.

| Component | What it is |
|---|---|
| Staff create accounts | Not a stretch idea and not a goal — the *only* one the goals assumed. Goals 3, 5 and 7 take an instructor by id, and until this the sole thing that could produce one was the seed script |
| Public timetable | The one screen that needs no account, and so the only part of the product a reviewer sees before signing in |
| Booking a whole term | The goal 7 generator's shape applied a second time: savepoint per candidate, a report of what happened |
| Room use and instructor pay | Two aggregates over one window, and three figures they deliberately refuse to compute |
| Waitlist position | Already built on the roster; it needed the number on the two screens where somebody is actually looked up |

The honest note on this session, written before session 9: **none of it was worth as much as the
deployment that was still not done.** That turned out to be right, and for a reason I had not predicted —
deploying did not just publish the software, it found defects that no amount of local work could have.
The brief is explicit that stretch ideas never substitute for a goal, and a live URL is a submission
requirement rather than a nicety. I did this work because the goals were finished and the features were
cheap, not because it was the most valuable thing left.

### Session 9 — Deployment

The plan said "create the database, give the server its connection details, point the browser at it". That
part took about an hour. The rest of the session was spent on things that were only *visible* once it was
real, and they are the reason this session was worth more than the features in session 8.

**What went up.** Supabase on `ap-south-1`, PostgreSQL 17.6 — one major behind local, and nothing in the
migrations needed anything newer. All the migrations applied unchanged in six seconds, every extension
created, every trigger and exclusion constraint intact; I checked the append-only guarantee by trying to
`TRUNCATE booking_events` against the live database and watching it refuse. The seed then ran and committed
112 sessions and roughly 1,300 bookings. A Render Web Service for the API, a Render Static Site
for the SPA, and the `/api/*` rewrite that keeps them on one origin.

**Four things deploying taught me that building had not.**

1. **The region pair was wrong, and it cost 3–4 seconds a page.** The API went to US West against a
   database in Mumbai: ~230ms per round trip, several round trips per request. `architecture.md` already
   said regions must be pinned. Knowing the rule did not stop me breaking it, and only measuring found it.
2. **Most of a request was not the query.** Profiling a trivial endpoint gave 100ms of query and 475ms of
   overhead — a connection validation ping and two separate `SET LOCAL` statements, three round trips paid
   on every request regardless of what it asked for. That is why `/rooms` returning 193 bytes cost the same
   as the whole dashboard. Merging the timeouts into one `set_config` call and dropping `pool_pre_ping`
   took a measured request from 694ms to 339ms.
3. **The seed was slow in a way that was information, not a nuisance.** Against localhost it takes seconds;
   against a remote database it took twenty-five minutes, because it books one member at a time with a lock
   and an audit event each. That is the round-trip cost of the booking path made visible — the same cost a
   real user pays once, multiplied by thirteen hundred.
4. **Schema before code is the wrong order.** I applied the unique-title migration ahead of the code that
   translates its constraint, and for a few minutes the database refused duplicates while the running app
   returned a 500 instead of a 409.

**The interface changed too.** Every paginated list had kept its previous page on screen while the next
loaded — invisible polish at 3ms, a lie at 300ms, because the header said one week while the rows described
another. Removed everywhere (Decision 9). It is the clearest example in the project of something that was
correct locally and wrong in production.

**Keeping it awake.** Render sleeps after 15 minutes and Supabase pauses after a week, so an UptimeRobot
check hits `/health/ready` every five minutes — one monitor for both, because the endpoint that proves the
database is reachable is also the request that resets its timer.

**Where it ended up.** `/public/schedule` went from 6.5s to 1.6s and `/health/ready` from 2.4s to under
0.9s, combining the region move with the round-trip fix. The remaining ~0.4s floor is Render's shared CPU
on a request that touches no database at all, and no amount of query work goes below it.

### Session 10 — Self-service booking, on a branch

The largest stretch idea in the brief, and the only one that changes who the
software is *for*. Built on `feature/new` rather than `master`, because Render
deploys every push to `master` and a half-finished third role is not something to
publish one commit at a time.

**Seven components, in an order chosen so each one could be wrong on its own.**

1. **The principal.** Where a member's password lives, which turned out to be the
   whole design — see below.
2. **Authorization.** Every existing role decision revisited before any member
   feature existed, because that is where the bugs were going to be.
3. **Provisioning.** Staff switch on a login for one member at a time.
4. **Reads.** `/me/membership` and `/me/bookings`, to prove the scoping held
   before any write path could exploit a hole in it.
5. **Writes.** Booking and cancelling, through the same service the desk uses.
6. **The interface.** A shell of the member's own.
7. **Documentation**, which is this.

**The decision that shaped everything was where the credentials live**, and my
own note from session 2 was wrong about it. `models/member.py` had said since the
beginning that this phase would add `password_hash` to `members`. It cannot:
every write names its actor as a foreign key into `users`, so a member booking
their own place has nothing valid to put in `bookings.created_by`. Solving that
from the `members` side means teaching the append-only timeline about two species
of actor — the one table in this schema that can never be revised afterwards.

A `users` row with `role='member'`, linked from a nullable `members.user_id`,
costs one column and leaves every existing member untouched. It also paid a
dividend I had not predicted: because the actor is the member's own account,
goal 9's history distinguishes "the member booked themselves" from "the desk
booked them" for free, with no new column and no new event type.

**The risk I expected was the role binary, and it was real.** Every role check in
this codebase was written when there were two, as `if staff … else instructor`.
There were eighteen, and a third role makes every `else` reachable by somebody it
was not written for. They fail closed — a member matches no instructor row, so
filters return nothing and guards return 403 — safe rather than harmless. The one
that would have mattered is the instructor picker, and Decision 3 says why.

**What I decided not to build matters as much as what I did:** there is no sign-up
page, for reasons that are Decision 5's rather than this document's. The planning
consequence is the part that belongs here — because staff switch a login on rather
than a stranger creating one, **payment never entered the feature**, and a session
I had budgeted days for became a single component.

**Estimated against actual.** I expected the interface to be the bulk and the
authorization to be a morning. It was the other way round: the backend
groundwork and the eighteen role decisions took roughly twice the two screens,
and the screens were quick because the member's shapes were already decided by
the time I opened a `.tsx` file. The one surprise was that the member side needs
no timezone handling at all — every date, time and "has this passed" arrives from
the server already settled — which deleted a whole category of work I had
budgeted for.

**41 tests came with it**, and nine of them are walls rather than features: every
studio endpoint refuses a member, a member cannot book through the staff route
even for themselves, two members on one session each see exactly one row, and the
timeline records the member as the actor. The last one is asserted by reading the
role straight off `booking_events.actor_user_id`, because "goal 9 gets this for
free" is a claim worth checking rather than asserting.

## The three places my order was wrong

**I set the database up earlier than planned, and should have planned it that way.** Local PostgreSQL was
scheduled after the database layer. Moving it forward and running my platform assumptions as plain SQL
*before* writing a migration caught five things at design time that would otherwise have arrived later as
confusing failures — including that `timestamptz + interval` cannot be a generated column, and that
extensions are per-database rather than per-cluster. It also caught a claim in my own schema document
that was simply false. Half an hour that repaid itself the same afternoon.

**The seed had to come last, and I wanted it early.** I wanted demo data at the start so I could click
through something. It could not work that way: the seed drives the real services, so it cannot exist
until every write path does. Doing it early would have meant inserting rows directly, and then the demo's
audit timelines would have been fixtures *shaped* to look like the system's own rather than actually
being them — which defeats the point of showing them to anybody.

**The backend was not finished when I announced it was.** I declared it complete and moved to the
interface, and building the interface immediately found three things missing that no amount of rereading
the API would have shown me:

- Goals 3, 5 and 7 all take an instructor **by id**, and nothing in the API could turn a person into one.
  There was no endpoint listing instructors, so the only way to schedule a class was to read a uuid out
  of the database by hand.
- `GET /bookings/{id}/timeline` returned events with no booking attached, and nothing fetched a booking
  by id — so a history screen could show what happened, but not whose history it was.
- `booked_count` counts *active* bookings. That is correct for capacity, and it drops to zero once a
  class is settled, so a finished and fully attended class rendered as an empty room.

None of the three is visible from the endpoint list. All three are obvious the moment something has to
render. **Building a client is a test of an API in a way that reading it is not**, and I would now treat
"the backend is done" as a claim that only a consumer can settle.

## What I estimated versus what it took

The brief budgets about twelve hours. **I set that aside deliberately.** I would rather be able to explain
every line in this repository than finish inside a target, and the round after this one is a conversation
about specific decisions. So the honest comparison is not estimate against actual — it is where the time
went against where I expected it to go.

Overall it landed at roughly **60% backend to 40% frontend**. I would have guessed the interface was a
quarter of it at most. Both tables below are shares within their own half.

**Within the backend:**

| | Expected | Actual | Why |
|---|---|---|---|
| Design and documentation | ~20% | **~35%** | Two independent review rounds. The first found twelve critical issues; the second found eight *new* ones that the first round's fixes had introduced. Both were worth it |
| Schema and migrations | ~15% | ~10% | Verifying the platform first meant the migrations mostly worked the first time |
| Booking lifecycle (goal 4) | ~15% | ~15% | The only estimate that held exactly |
| The remaining goals | ~35% | ~25% | Faster than expected, because the layering and the visibility filter were settled before they were written |
| Tests | folded into the above | **~15% on their own** | Consistently underestimated. The concurrency suite alone took longer than goal 6 |
| Chasing wrong assumptions | 0% | ~5% | Not budgeted at all. Listed below |

**Within the frontend**, where the split surprised me more:

| | Expected | Actual | Why |
|---|---|---|---|
| Design direction and the drawn canvas | ~10% | ~10% | The one that held. Four screens drawn, argued and revised before any React existed |
| Foundation — tokens, client, query layer | ~15% | ~20% | The single-flight refresh and the token store took longer than the screens they hold up |
| The screens | ~50% | **~30%** | Much faster than expected. Primitives and domain atoms built first meant most screens were assembly |
| Visual passes — type, colour, ground, motion | ~10% | **~30%** | Four display typefaces, three ground treatments, two palettes, one intro animation. Almost none of it changed what the software *does* |
| Validation, accessibility, closing the API gaps | ~15% | ~10% | The gaps were cheap to close once the client had proved they existed |

**What I got most wrong: how long verification takes relative to writing.** Writing the dashboard query
took twenty minutes. Working out *why* it failed took longer than that, because the cause was an obscure
SQLAlchemy parsing rule rather than anything in the query itself. That ratio repeated all the way through
the project, and next time I would budget for it explicitly instead of treating it as overhead.

**What I got second-most wrong: how much of interface work is not engineering.** The screens took less
time than the passes over type, colour and ground that followed them, and those passes produced almost
nothing that changes what the software does. I do not think that time was wasted — an interface somebody
opens every morning earns it — but I had it filed under "polish" and it is closer to a third of the front
end.


## What I cut, and why

**What I would have cut at hour twelve.** I ran to about 16–18 hours against the brief's 12, so the
honest version of this question is not "what did I drop" but "what would have gone if I had stopped on
budget". In order: the four stretch ideas built after the ten goals were done, which is roughly three
hours; the second review round in §5 of `ai-prompts.md`, which cost about two and found eight real
defects — I would have regretted it; and the visual passes, where I spent roughly three times what I
planned. The ten goals, the concurrency suite and the deployment would all have survived, because
everything on that list is either the brief itself or the evidence that the brief was met.

Everything below was cut for **scope discipline** rather than for time, which is a different list and a
more useful one.

| Cut | Why |
|---|---|
| The whole Redis, pub/sub and WebSocket layer | Serves no goal, and still does not now that members can book for themselves: self-service goes directly to Booked or Waitlisted exactly as the desk does, so there is no deliberation window to protect and nothing that needs one person's screen to change because of another's action. Documented at length instead of built |
| A least-privilege `app_rw` database role | Built, applied, then deleted. The triggers already satisfy goal 9 on their own, and the role added a second credential and real deployment risk for defence in depth behind a guarantee that already held |
| An `events/` package with a post-commit dispatcher | Its only behaviour was logging. The same seam exists for free by returning events from the service |
| A `metadata jsonb` column on the audit log | An unstructured escape hatch in an append-only table is where schema discipline goes to die |
| An idempotency-key store | The partial unique index already turns a double-submitted booking into a clean 409 |
| Multi-tenancy, per-row timezones, GraphQL, SSR, a job queue | Each recorded in `architecture.md` with its reason |
| A component library — MUI, Chakra, shadcn | Ten screens with one deliberate visual identity. A kit is faster for the first screen and then argues with you for every one after it. Radix supplies the two components where being wrong is a bug rather than a style: the dialog's focus trap and the popover's positioning |
| A client-side store — Redux, Zustand | Nearly everything here is server state, and TanStack Query owns that. What is genuinely client state is a token and a theme, and both are about twenty lines of `useSyncExternalStore` |
| A charting library | One static eight-week bar chart. Sixty lines of `div`s beat a dependency, and the result matches the palette by construction rather than by configuration |
| Notifications and payments | No goal asks for them, and both need infrastructure this deployment does not have. Self-service member booking *was* built later — session 10 |

**Six things here are not goals**, and I have kept that distinction sharp rather than quietly folding
them in. Staff creating accounts is the only one the goals actually *assumed* — they take an instructor
*by id*, and until that endpoint the only thing that could produce one was the seed script. The other
five are stretch ideas from the brief: the public timetable, booking a whole term, room utilisation,
instructor payroll, waitlist position, and self-service booking.

## What is still outstanding

Stated plainly rather than left implied.

1. **Infrastructure as code.** The deployment itself is done and verified, but it lives in two Render
   dashboards rather than in this repository: no `render.yaml`, no Dockerfile. A reviewer can read every
   decision in this project except how it is actually wired together, and the same-origin rewrite is one of
   the more interesting ones. Migrations are also a manual step now, by choice (session 9) — defensible at
   one instance, the first thing to change at two.
2. **CI and error reporting.** The keep-warm monitor is built — UptimeRobot on `/health/ready` every five
   minutes — but these two are not. `ruff`, `mypy --strict`, 415 backend tests, `tsc`,
   `eslint --max-warnings 0` and a production build all run green locally on every change, but nothing
   enforces that on push. Recorded as known weaknesses rather than described as done.
3. **No automated frontend tests.** The backend has 415; the interface has a typechecker, a linter, a
   build and a person clicking through. Every screen was exercised by hand against the seeded database and
   both roles were walked end to end, but there is no regression net — a refactor that breaks a screen is
   caught by somebody noticing. Of everything on this list this is what I would do first with more time,
   starting with the booking dialog and the roster, because that is where the logic actually lives.
4. **The interface has not been opened on a phone.** It is built responsively and capped for reading, but
   "responsive by construction" and "checked at 390px" are different claims, and only the first one is
   true here.

Sessions 7 and 8 are why I am wary of calling anything on that list small. Every feature in session 8
turned up a defect in passing — a migration whose `downgrade` had never been run, a public endpoint that
truncated in silence while claiming a full window, a substitute swap that returned the previous
instructor. None of them were in the feature; all of them were found by building it. Every defect in it was found by using
the software rather than by testing it, and that is not a technique I can put in a suite. It is just the
observation that the last hour of clicking around has, so far, always found something.
