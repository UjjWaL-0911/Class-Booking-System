import type { BookingQuery } from '@/api/bookings'
import type { MemberQuery } from '@/api/members'
import type { SessionQuery } from '@/api/sessions'
import type { Uuid } from '@/api/types'

/**
 * Every cache key in the app, in one place.
 *
 * Not a style preference. A booking changes three things at once — the session's
 * seat counts, the bookings list, and the dashboard figures — and each of those
 * is fetched from a different screen. Keys written inline at each call site
 * drift, and the symptom is a seat count that stays wrong until someone reloads.
 */
export const keys = {
  me: ['me'] as const,

  dashboard: ['dashboard'] as const,

  alerts: ['alerts'] as const,
  alertCount: ['alerts', 'count'] as const,

  classes: (includeArchived: boolean) => ['classes', { includeArchived }] as const,
  rooms: ['rooms'] as const,
  teachers: ['teachers'] as const,
  publicSchedule: (days: number) => ['public-schedule', days] as const,
  operations: (from: string, to: string) => ['operations', { from, to }] as const,

  sessions: (query: SessionQuery) => ['sessions', query] as const,
  session: (id: Uuid) => ['sessions', id] as const,

  members: (query: MemberQuery) => ['members', query] as const,
  member: (id: Uuid) => ['members', id] as const,

  bookings: (query: BookingQuery) => ['bookings', query] as const,
  bookingTimeline: (id: Uuid) => ['bookings', id, 'timeline'] as const,

  // The member's own surface. Kept apart from the studio keys because they are
  // a different person's view of the same studio: signing out clears everything
  // anyway, but a shared key would let one role's cache answer the other's read.
  myMembership: ['me', 'membership'] as const,
  myBookings: ['me', 'bookings'] as const,
  mySchedule: (days: number) => ['me', 'schedule', days] as const,
  myClasses: ['me', 'classes'] as const,

  /** The roster of one session: every booking on it, including the waitlist. */
  roster: (sessionId: Uuid) => ['bookings', { session_id: sessionId }] as const,
}

/**
 * What to invalidate after a write that changes a booking.
 *
 * Broad on purpose. The alternative — patching each affected cache entry by hand
 * — means reimplementing the promotion rule on the client, and the client is the
 * one place in this system that must never hold an opinion about who gets a freed
 * spot.
 */
/**
 * What a rate change affects.
 *
 * The list, obviously — and the operations report, because its payroll figures
 * are computed from this number. Leaving yesterday's total on the reports screen
 * after a raise would be showing somebody a figure the server no longer agrees
 * with. `['operations']` is the prefix, so every window in the cache goes.
 */
export const rateWriteAffects = [['teachers'], ['operations']] as const

/**
 * What a member booking or cancelling affects.
 *
 * Both their own lists, because every schedule row carries their status on it
 * and the seats left — so taking a place changes the list they took it from.
 * `['me']` is the prefix, so every cached window goes at once.
 */
export const memberWriteAffects = [['me']] as const

export const bookingWriteAffects = [
  ['bookings'],
  ['sessions'],
  ['dashboard'],
  ['alerts'],
] as const
