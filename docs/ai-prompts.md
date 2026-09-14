# AI prompts

The prompts you actually used, in the order you used them, grouped by what you were trying to achieve. For each significant one: what you asked, what you got back, and what you had to correct.

Include at least one prompt that produced something wrong, and what you did about it.

If you did not use AI at all, say so here, and describe your process instead.

---

## How I used AI on this project

Claude as a design partner and an implementation accelerator, not an autopilot. One rule set at the
start and kept to: **discuss and agree the design of a module before any code is written for it.**

The rule that did the most work on the build side was smaller: **stop and tell me rather than working
around it.** A model asked to make a screen work will make the screen work, and the compromise
disappears into the code where nobody reviews it. Instructed to stop, it surfaced three things the API
could not do (§11) instead of hiding three workarounds in the client.

This is a consolidation, not a transcript. Related exchanges are merged; the hundreds of small ones —
"run the tests", "why is this 500ing" — are not here. What is here is what changed the shape of the
thing. §1–6 are design, §7–9 the backend, §10–14 the interface, §15–17 the work past the ten goals.

**Five entries are about catching something wrong, and they fail in five different ways** — the part of
this file I would want read most closely:

| § | What went wrong | How it was caught |
|---|---|---|
| 3 | An answer that was **wrong** — a Redis architecture for a problem Postgres already solves | Arguing with it instead of accepting it |
| 6 | An answer that was **right but unexamined** — the correct call, defended by assertion | Asking for the case against my own decision |
| 9 | **My own documentation** drifting from the code while both were written | Checking whether each claim's file existed |
| 12 | Code **correct against the field name and wrong against reality** | Real seeded data, on a class that had finished |
| 13 | **My own prompt** being ambiguous, and me repeating it louder | Naming the three exact phrases I meant |

---

## 1. Absorbing the brief and locking the stack

### Prompt

> Read the attached assignment README and SUBMISSION template in full. Before proposing anything, I
> want you to demonstrate that you have understood it:
>
> 1. Summarise the business scenario in one paragraph.
> 2. Take the 10 required goals and group them by implementation risk — separate the routine CRUD
>    from the parts where the real difficulty sits, and say specifically what makes the hard ones
>    hard.
> 3. Identify the requirements that candidates most commonly miss or under-implement, reading the
>    exact wording rather than the bold headline of each goal.
> 4. Note anything the brief grades that is *not* the application itself.
>
> Do not propose a stack or a plan yet.
>
> Follow-up, once we had agreed the reading: I will use FastAPI for the backend, PostgreSQL on
> Supabase for the database, and deploy on Render. For the frontend I am deciding between React and
> Next.js. Assess that stack against this specific brief, tell me if any part of it is a poor fit,
> and give me a recommendation on the frontend question with your reasoning rather than a preference.
>
> Separately: explain what an ORM is from first principles, then explain concretely what it buys me
> *in this project* — tie it to specific goals — and what the costs and trade-offs are, so I can
> defend the choice in an interview.

### What came back, and what I changed

A reading of the brief that separated the routine CRUD from the three goals where the difficulty
actually sits — capacity under concurrency, the immutable timeline, and the alert that must re-trigger
— plus the observation that the brief grades the *documentation and the git history*, not only the app.
That reframing set the whole plan.

On the stack it argued for React over Next.js: everything here is behind a login, so SSR and file-based
routing buy nothing, and a framework whose main advantages are unusable is a dependency rather than a
choice. I took that.

## 2. Designing the concurrency control

### Prompt

> Walk me through the concurrency control you would build for the booking engine, before writing any
> code. Structure it as follows:
>
> 1. Enumerate every race condition this system can actually experience. For each one, state the
>    concrete interleaving and the incorrect outcome it produces — do not just say "race condition".
> 2. For each race, name the mechanism that prevents it, and justify that mechanism against the
>    alternatives you rejected.
> 3. Be explicit about the isolation level and the locking strategy, including *why* that isolation
>    level rather than `SERIALIZABLE`.
> 4. Cover lock ordering and deadlock avoidance across every operation that takes more than one lock.
> 5. Separate what the database enforces from what the application enforces, and explain where you
>    draw that line.
> 6. Describe how each race would be proven fixed by an automated test.
>
> Reference the specific goals in the brief that each mechanism satisfies.

### What came back, and what I changed

The design this project still runs on: `SELECT … FOR UPDATE` on the session row, `READ COMMITTED`
rather than `SERIALIZABLE`, the database/application line drawn explicitly, and a named test for each
race. Asking for *the concrete interleaving and the incorrect outcome* rather than "the race conditions"
is what made it specific enough to build from.

**What I corrected:** it proposed locking `bookings`. The invariant is about a *set* of rows that do not
exist yet, so the lock has to be on the parent — which is also what keeps different sessions from
blocking each other.

## 3. The prompt that produced the wrong answer — over-engineering the architecture

### Prompt

> I want to tackle concurrency and consistency under load properly. In an event-booking system the
> architecture normally contains:
>
> - horizontal scalability
> - Redis for a live seat map and for holding seats
> - Redis pub/sub
> - real-time WebSockets fanned out over Redis pub/sub
> - asynchronous background jobs (BullMQ or similar)
> - database connection pooling trade-offs
> - pessimistic locking
>
> Act as a senior developer. Integrate these into one architecture, critically review the trade-offs
> of each, add anything important that is missing, and give me a final integrated plan. Make it a
> real-world design of the kind RedBus or BookMyShow would run.

And then, once I had read it:

> Re-read the README against the architecture you just proposed. Is the self-service booking flow
> that Redis seat-holds, pub/sub and WebSockets exist to serve actually required by any of the ten
> goals — or am I over-engineering this? Argue it from the specific wording of the brief, and cite
> the goals.

### What came back, and what I changed

**The prompt that produced the wrong answer, and the most useful entry in this file.** I got exactly
what I asked for: a genuinely good architecture with Redis seat-holds, pub/sub, WebSocket fan-out and a
job queue. It was competent and it was wrong for this brief.

**What I corrected:** I did not accept it. The follow-up above forced it back to the source text, and
the answer came back that goal 4 books **directly** to Booked or Waitlisted — there is no deliberation
window for a seat-hold to protect, and no goal requires one person's screen to change because of
another's action. All of it went.

**The failure was mine, not the model's.** I had framed the question around a solution and named two
systems whose scale is nothing like a studio where classes fill over days. Ask for an integration of a
list of technologies and you will get one. The lesson I actually took: *state the problem, never the
shape of the answer.*

## 4. Designing the database schema

### Prompt

> Draft the complete database schema. Requirements:
>
> - Cover all ten goals — walk each goal and show which tables and columns serve it.
> - Give every table's columns with exact Postgres types and constraints.
> - State which relationships are one-to-many and which are many-to-many.
> - Draw an explicit line between constraints enforced by the database and rules enforced by the
>   application, and justify where you put that line.
> - Call out anything you are deliberately denormalising, and what it costs.
> - Identify what would break first at 100x the data.
> - Where you had to make a judgement call, do not silently pick — surface it as an open question
>   with your recommendation and reasoning, so I can decide.
>
> Two constraints: the audit timeline must be genuinely immutable, enforced at the database level and
> not by convention, because goal 9 says even studio staff cannot edit it. And the expiring-membership
> alert must re-trigger when an extended expiry date falls back inside the seven-day window — design
> that so it works without a background job.

### What came back, and what I changed

The schema more or less as it stands. Two requirements in the prompt did the work — "enforced at the
database level and not by convention", which produced the append-only triggers rather than a code
comment, and "design that so it works without a background job", which produced the dismissal keyed to
the expiry *value*.

**What I corrected:** it first proposed a `booked_count` column. That is precisely the value that drifts
under concurrency, and rejecting it is why every occupancy figure in this system is computed under the
row lock. Asking it to *surface judgement calls as open questions rather than silently pick* is what
surfaced it at all.

## 5. Writing the architecture document, and having it attacked

### Prompt

> Write `docs/architecture.md`. It must answer the four questions in the template — the moving pieces
> and how they communicate, where each piece runs, the end-to-end request path for one representative
> user action, and what I decided not to build and why.
>
> Specific requirements:
>
> - For the request path, choose the action that exercises the most of the system, and justify that
>   choice. Trace it from the browser click through to the database and back, naming the actual
>   middleware, dependencies, transaction boundaries and lock acquisitions in order.
> - Be concrete about where server-side authorization happens and why the client-side route guard is
>   not a security boundary.
> - Be honest about free-tier constraints rather than describing an idealised deployment.
> - The "what I did not build" section is the one the brief says it is grading. Give it real weight —
>   including the real-time architecture we reversed out of, with the reasoning.
>
> Then have an independent reviewer critique it: check it against all ten goals, hunt for
> concurrency, pooling, auth and deployment risks it misses, and attack the weakest part of the
> argument the way a hostile interviewer would.

### What came back, and what I changed

The document, and then — because the second half of the prompt asked for it — a hostile review of my
own document. It came back with twenty-five findings, twelve of them critical, and one was the most
useful correction on this project: **the architecture doc was confidently wrong about the thing it was
proudest of.** I had described the deferred capacity trigger as a backstop catching "a future code path
that forgets the lock". It does not. A deferred trigger runs at commit inside the committing
transaction, so its `count(*)` sees committed rows plus its own — two transactions that both skipped the
lock would each pass. A false guarantee is worse than none, and it now takes the lock itself.

**What I corrected:** I sent the fixes back for a second pass asking it to *verify* rather than
re-derive. That round closed twelve of twelve and found **eight new defects introduced by the first
round's fixes** — which is the thing worth knowing about review rounds: they do not converge on the
first pass, and the fixes are themselves changes.

What I kept from it was a habit rather than a phrase: **every present-tense claim about infrastructure
gets checked against a file before it ships.** §9 is that habit turned into a prompt.

## 6. Stress-testing my own decision to leave Redis out

### Prompt

> Three questions, in order, and answer each before moving to the next.
>
> 1. Audit the current design against the ten goals: is Redis used anywhere in what we are actually
>    building? Go component by component — locking, dashboard caching, the nav alert badge, rate
>    limiting, job queueing, idempotency — and for each say what we use instead and why.
> 2. Same audit for WebSockets. Walk each of the ten goals and identify any that require the server
>    to initiate a message to a client that did not ask for it. If none do, say what we use instead
>    and what a push channel would actually cost to build correctly.
> 3. Now challenge the conclusion. Suppose the studio grows to 1,000–2,000 members and self-service
>    booking exists. Without Redis, every request goes to Postgres and serialises on one session row.
>    Does that not make the database a bottleneck? Argue that a member base can grow at any studio,
>    and that Redis is the standard answer for exactly this problem.
>
> For the third question specifically, I do not want a qualitative reassurance. Give me the
> arithmetic: what is the actual per-session throughput ceiling of the current design, at what
> concurrency does it start rejecting requests, what exactly does Redis remove and what does it not,
> and what would you do first, second and third before reaching for it. If the numbers show I am
> right, say so.

### What came back, and what I changed

This is the prompt I would keep if I could keep one. §3 tested a decision I suspected was wrong; this
tested one I believed was right, which is harder and rarer.

Refusing a qualitative answer is what made it work. The arithmetic came back: cancel-and-promote is
eight statements, so the lock is held ~8–10 ms, one session sustains **100–125 bookings/second**, and
contention roughly 300 deep starts returning 503 under a 3-second lock timeout. Sessions are
independent, so this scales with the timetable. Redis removes the round trips and does **not** remove
the need for the database to be the final arbiter of a seat.

The conclusion held, but it went from an assertion into a number with an escalation order behind it —
and the number is now quoted in three other documents.

## 7. Verifying the platform before building on it

### Prompt

> Before we write a single migration, take every claim in `schema.md` and `architecture.md` that
> depends on how PostgreSQL actually behaves, and turn each one into SQL we can run against the local
> database. Specifically:
>
> 1. That `timestamptz + interval` cannot be used in a generated column.
> 2. That a GiST exclusion constraint over `(uuid WITH =, tstzrange WITH &&)` works, partial on
>    `deleted_at IS NULL`, and that adjacent-but-not-overlapping sessions are accepted.
> 3. That a `DEFERRABLE INITIALLY DEFERRED` constraint trigger accepts a `WHEN` clause, can take a row
>    lock inside its function, and fires at `COMMIT` rather than at `INSERT`.
> 4. That `BEFORE TRUNCATE` closes the hole a row-level trigger leaves.
> 5. That a trigram index serves `ILIKE` on a `citext` column.
>
> For each: state what you expect, run it, report what actually happened. Where the result contradicts
> the documentation, correct the documentation rather than the expectation.

### What came back, and what I changed

Five claims turned into runnable SQL before a migration existed. Three held. Two did not, and both
would have been expensive later:

- `timestamptz + interval` **cannot** be a generated column — generated columns need an `IMMUTABLE`
  expression and that one is only `STABLE`. `ends_at` is trigger-maintained because of this.
- A trigram index on a `citext` column **creates happily and is then never used**, because the planner
  will not use it for a citext-native operator. An index that exists, reports as valid, and does
  nothing. The fix is `(email::text)` in the index *and* the cast in the query.

**What I corrected:** the instruction that mattered was the last line — *where the result contradicts
the documentation, correct the documentation rather than the expectation.* Two sentences in `schema.md`
were simply false and would have survived any amount of re-reading.

## 8. Building the booking engine, and proving the tests can fail

### Prompt

> Implement the booking lifecycle from goal 4. Requirements:
>
> - Every operation that can change a session's Booked count or its waitlist takes
>   `SELECT... FOR UPDATE` on the session row first, and counts under that lock.
> - The state machine rejects every illegal move with a message naming the actual reason, because goal
>   4 requires the rejection to explain why.
> - Cancelling a Booked booking promotes the earliest eligible waitlisted member **in the same
>   transaction**.
> - Every status change appends to the immutable timeline through one function.
>
> Then write concurrency tests that run N genuinely parallel transactions — separate sessions on
> separate connections — against real PostgreSQL.
>
> Finally, and this is the part I care about most: **delete the row lock, run those tests again, and
> show me which ones fail.** A concurrency test that passes with and without the lock is worthless, and
> I would rather find that out now than in an interview.

### What came back, and what I changed

The engine, and the part of the prompt I care about most: **delete the row lock and show me which
tests fail.** Several did, exactly the ones that should — 20 parallel bookings for 12 seats oversold;
two concurrent cancellations promoted the same waitlisted member twice.

A concurrency test that passes with and without the lock is worthless, and there is no way to know which
kind you have without removing the lock. Every concurrency test in this suite has been seen to fail.

## 9. The audit that found the documentation lying

### Prompt

> Two questions, and answer both by checking rather than from memory:
>
> 1. Is the backend actually complete for phase 1? Enumerate the registered routes and map them to the
>    ten goals.
> 2. Is the seed data present in the database? Query it.
>
> While you are in there, go through every present-tense claim `architecture.md` makes about
> infrastructure — logging, rate limiting, CI, error reporting, local tooling, tests — and check
> whether the thing exists. Report anything the document asserts that the repository does not contain.

### What came back, and what I changed

The dullest prompt here and among the most valuable. The routes mapped to the goals and the seed was
present — but the claim audit found **six things `architecture.md` asserted in the present tense that
the repository did not contain**: structured logging with a request id, the rate limiter, CI, error
reporting, a `docker-compose`, and a coverage threshold.

**What I corrected:** each one either got built or got marked "not yet built". Documentation written
alongside code drifts *from* the code, because the document is written in the tense of intention. Every
present-tense infrastructure claim in this project has since been checked against a file.

## 10. Getting a design direction before any React existed

### Prompt

Consolidated from the design brief and the two rounds that followed it.

> Establish the visual design direction for this frontend before writing any code. It is a back-office
> tool for a fitness and dance studio, replacing a paper sign-up sheet and a membership binder. The
> backend is complete: 37 endpoints, ten goals, two roles. Draw four screens as a canvas I can judge —
> the dashboard, the week, the bookings list and one session — and make the typography and the
> dashboard treatment do actual work. My first instinct was conventional and I want you to argue me
> out of it.
>
> Second round, after the first build: this looks like boxes everywhere and the nav bar looks like it
> is coming out of the page. Redesign it so it reads as modern. I have put a reference image in
> `design/`. Also design a landing page — and the landing page is **not** the login page.
>
> Third round: the theme should be brown and beige for light mode, with darker browns and beiges for
> dark. The landing page should stay light whatever the app theme is, with a light source and some
> grain, and a slightly darker ground than pure cream. The platform is about physical fitness, so put
> something of that on the landing page rather than generic marketing shapes.

### What came back, and what I changed

Four screens drawn and argued before a line of React existed, with the instruction to *argue me out of*
my first instinct — which was the conventional card-grid dashboard. It did, and the thing that replaced
it is a headline sentence in plain English with the numbers set in it.

**What I corrected, across three rounds:** the first build read as boxes inside boxes, and the fix was
to delete the boxes rather than restyle them — space does the separating now. The landing page is
deliberately not the sign-in page, which is a distinction a back-office tool usually gets wrong.

## 11. Building the interface in one pass, and what it exposed in the backend

### Prompt

> Build the frontend against the agreed design. Constraints I care about:
>
> - React, Vite, TypeScript strict. No file over 250 lines.
> - Every colour, size and weight is a design token, so a token swap repaints the whole app.
> - Server state is TanStack Query and nothing else. Do not add a state manager.
> - No component kit. Bring in a dependency only where getting it wrong is a *bug* rather than a
>   style — say which ones those are and why.
> - Each screen maps to the goals it serves. Nine screens, not nine screens plus features nobody asked
>   for. We fulfil the ten goals — not less and not more.
>
> If you find something the API cannot do, stop and tell me rather than working around it in the
> client.

### What came back, and what I changed

The interface, against the agreed design, with three constraints that shaped the code more than any
styling decision: no file over 250 lines, every colour and size a token, and TanStack Query as the only
state manager.

**The instruction that earned its place was the last one** — *if you find something the API cannot do,
stop and tell me rather than working around it in the client.* It stopped three times. Each was a real
gap, and each was fixed in the **API**: the roster needed one call rather than N, the alert badge needed
a count endpoint rather than fetching the feed, and the session payload needed attendance counts. A
model told to make it work would have assembled all three in the browser, where the rule would then have
lived in the wrong place.

## 12. The frontend prompt that produced something confidently wrong

### Prompt

> Draw the occupancy on every screen that shows a class: how full it is, how many are waitlisted, and
> whether anyone still needs marking.

### What came back, and what I changed

**The most instructive bug in the project, and no review would have caught it.** The code was correct
against the field it read: `booked_count` counts bookings *currently* Booked. It is also **zero once a
class is settled** — so a finished, fully attended class rendered as an empty room.

It survived every backend test, because no backend test asks what a *screen* should show. It was found
by opening the seeded data on a class that had already happened.

**What I corrected:** the session payload now carries `attended_count` and `no_show_count`, and one
shared helper adds the three. The wider lesson is in the closing section: review checks a system against
its own assumptions; only real data checks the assumptions.

## 13. The prompt that was wrong on my side

### Prompt

> The words on the landing page are cut. Don't cut them, write them normally.

Then, when the first fix did not help: *"the words on the landing page are still cut"*. Then, when the
second did not either: *"They are still cut man"*. And finally, naming them: *"The sign-up sheet, the
waiting list in the margin, the membership binder — these are the words which are cut."*

### What came back, and what I changed

A prompt that was wrong on my side, included because the file would be dishonest without one. "Cut"
meant three different things — a heading clipped by `overflow`, copy I had shortened, and a line broken
mid-phrase. The model fixed the first, I repeated myself more forcefully, and we went two rounds.

**What I corrected:** naming the three exact phrases. Adding emphasis to an ambiguous instruction adds
emphasis, not specificity — which is not a lesson about AI at all.

## 14. Contrast and validation as arithmetic rather than taste

### Prompt

Consolidated from several rounds of palette and form work.

> Two standing rules for the rest of this build.
>
> 1. Before you write a colour, compute its WCAG contrast ratio against the ground it sits on and tell
>    me the number. Do not adjust by eye and do not tell me something "looks fine".
> 2. Add input checks everywhere input is taken — a wrong email format should be refused with a reason.
>    Mirror the server's rules rather than inventing stricter ones, and verify that against the running
>    server rather than assuming.

### What came back, and what I changed

Two standing rules rather than a task, and both replaced a judgement with an arithmetic.

Computing WCAG ratios before writing a colour caught four combinations that "looks fine" would have
passed, including the waitlist amber on the card ground. Mirroring the server's validation *verified
against the running server* rather than invented caught a client rule stricter than the API's, which is
the failure mode nobody notices because it only rejects valid input.

## 15. Three stretch features, and what building them found

### Prompt

> The ten goals are done. Review the brief's stretch ideas, rank them by the visibility I gain against
> the complexity of building them, and estimate each one against *this* codebase rather than in the
> abstract. Then implement the ones that rank well.
>
> Follow-up, once the ranking existed: implement recurring term bookings, room utilisation reporting and
> instructor payroll, and update the docs so they do not fall behind.

### What came back, and what I changed

A ranking that was more useful than the features. Two things became obvious that I had not
articulated: **waitlist position was already built** — the roster had shown a queue number all along —
and **"for members" was undeliverable as written**, because members had no accounts, so the honest
version was the desk being able to answer the question. (§17 is where that stopped being true.)

**Every one of the three features turned up a defect that was not in the feature.** A migration's
`downgrade()` that had never been run passed an already-prefixed constraint name; the public schedule
truncated in silence while claiming a full window; a substitute swap returned the previous instructor,
because `expire_on_commit=False` left a stale relationship in the identity map.

## 16. Deploying it, and the four defects that only existed in production

### Prompt

> Let's do the deployment. Tell me how — I would rather drive it manually than have it done for me.
>
> Follow-ups, as each problem appeared: every page takes three to four seconds since I moved to Supabase,
> what techniques can reduce that; the timetable shows last week's rows until the new week arrives, mark
> that data invalid the moment it is clicked; UptimeRobot says my backend is down but the site works.

### What came back, and what I changed

A runbook, and then a much more useful habit: **measure before recommending.** The first latency answer
could have been a list of plausible optimisations. Asking for measurements produced a breakdown that
made most of that list irrelevant — a trivial request spent 100 ms on its query and 475 ms on overhead,
paid identically whether an endpoint returned 193 bytes or a whole dashboard.

**What I corrected:** the first benchmark was too small and I nearly shipped its conclusion. Six runs
said merging the timeout statements gained nothing; twenty interleaved runs said 16%. *Measure, then
measure enough.*

**Four defects that no local work would have found:** the API deployed to a region ~230 ms from its
database, while `architecture.md` already said "regions are pinned"; every list keeping its previous
page, which is polish at 3 ms and a lie at 300 ms; a schema change shipped ahead of the code that
understood it; and health endpoints answering 405 to `HEAD`, because Starlette adds HEAD to a GET route
and FastAPI's `APIRoute` does not — so the uptime monitor reported the service down while it served
perfectly.

## 17. Self-service booking, and the feature I talked myself out of

### Prompt

> Brief me on the self-service booking feature before building any of it: what it
> actually is, the order of execution, and how it would finally be integrated.
>
> Then, as it was being built: there should be a sign-up page now so new members
> can sign themselves up, with only the functionality a member has — would that
> work?
>
> And after thinking about the answer: I would rather go with staff enabling
> self-service for a member, because I do not want to deal with payments and
> membership expiry. Would that work?

### What came back, and what I changed

The brief was the useful part, and specifically a line I had not asked for: **where a member's password
lives.** My own comment had said since session 2 that this phase would add `password_hash` to `members`.
It cannot — every write names its actor as a foreign key into `users`, so a member booking their own
place has nothing valid to record as the creator, and fixing it from the `members` side means changing
the append-only timeline.

**The second answer was better than my question.** I proposed a sign-up page; what came back was that it
works *only if signing up does not grant a membership* — because a membership implies payment, and a
public endpoint cannot know about payment.

**What I corrected: I dropped the sign-up page.** Not because it could not be made to work, but because
making it work honestly means a membership lifecycle and eventually payment — a product decision a
studio makes, not one a booking system assumes. What convinced me was the consequence: with staff
switching logins on, **payment never enters the feature at all**, because enabling an account does not
touch the expiry rule that decides whether somebody may book.

## What I would do differently next time

Four things, in the order I would apply them:

1. **Ask for the case against my own decision, not just for a review of it.** Section 6 is the prompt
   that did this and it is the most valuable one in the file. A review of a decision tends to improve
   how it is argued; a genuine case against it tests whether it survives.
2. **Demand the number, not the judgement.** "Compute the contrast ratio and tell me the figure" caught
   four things that "does this look readable" would have passed. The same shape works for query plans,
   lock hold times and response sizes — anywhere an opinion can be replaced by an arithmetic.
3. **Check that the claim's file exists.** Section 9's audit was the dullest prompt here and it found
   six documented features that were not built. It belongs before a submission, not after somebody asks.
4. **Add specifics, not emphasis.** Section 13 cost two rounds because I repeated an ambiguous word more
   forcefully instead of naming the three phrases I meant. That one is not about AI at all.

And one that is about the limits rather than the technique: **nothing in this list would have found the
occupancy bug in section 12.** Not a review, not a test, not an audit — the code was consistent with the
field it read, and the field was honest. It took seeded data that looked like a real studio's, and
somebody opening a class that had already happened. The useful conclusion is not that AI review is weak;
it is that review of any kind checks a system against its own assumptions, and only real data checks the
assumptions themselves.
