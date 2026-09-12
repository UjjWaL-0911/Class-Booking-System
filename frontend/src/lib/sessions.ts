import type { LocalDate, Session } from '@/api/types'

/**
 * Group sessions into days, keeping the server's order inside each.
 *
 * A `Map` rather than an object: insertion order is guaranteed, and the sessions
 * arrive sorted by start time, so the days and the classes inside them both come
 * out in the order somebody reads them.
 */
export function groupByDate(sessions: Session[]): [LocalDate, Session[]][] {
  const days = new Map<LocalDate, Session[]>()
  for (const session of sessions) {
    const existing = days.get(session.session_date)
    if (existing) existing.push(session)
    else days.set(session.session_date, [session])
  }
  return [...days.entries()]
}
