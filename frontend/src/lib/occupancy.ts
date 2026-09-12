import type { Session } from '@/api/types'

/**
 * How many people had a spot in the room.
 *
 * Not `booked_count`. That counts *active* bookings, which is exactly right while
 * a class is still ahead — it is what capacity is measured against — and becomes
 * misleading the moment the class is over: settling everyone as attended or
 * absent empties it, so a class that ran full reports zero.
 *
 * This was a real bug in this interface, found by looking at real data: a Vinyasa
 * class with seventeen attended and one absence drew as an empty room with two
 * people still waiting. The counts were right; the view was asking the wrong one
 * of them. Anything drawing the occupancy marks or saying "N of C" goes through
 * here.
 */
export function spotsTaken(session: Session): number {
  return session.booked_count + session.attended_count + session.no_show_count
}

/**
 * Whether the class is over.
 *
 * Compared against `ends_at` — an instant — rather than against the studio's
 * date, because "has it finished" is a question about a moment and not about a
 * calendar day. A class that ends at 19:00 is over at 19:01, not at midnight.
 */
export function hasFinished(session: Session): boolean {
  return new Date(session.ends_at).getTime() < Date.now()
}

/**
 * Whether the class has begun — and so whether it can still be booked.
 *
 * This is the line the server draws: `create` refuses a booking once
 * `starts_at <= now`, so a class that is under way is as unbookable as one that
 * finished last week. The distinction matters because `hasFinished` looks at
 * `ends_at`, and between the two is an hour in which a class is running and a
 * booking would be rejected.
 *
 * Used to decide what to *offer*, never to block a submission. The reference is
 * the browser's clock, and a browser clock a few minutes fast would otherwise
 * refuse a booking the server would have accepted — so a borderline case is
 * always allowed through to the server, which is the one that knows.
 */
export function hasStarted(session: Session): boolean {
  return new Date(session.starts_at).getTime() <= Date.now()
}

/** How many of the settled bookings are still unmarked. */
export function unmarkedCount(session: Session): number {
  return hasFinished(session) ? session.booked_count : 0
}
