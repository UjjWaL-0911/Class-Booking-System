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

  sessions: (query: SessionQuery) => ['sessions', query] as const,
  session: (id: Uuid) => ['sessions', id] as const,

  members: (query: MemberQuery) => ['members', query] as const,
  member: (id: Uuid) => ['members', id] as const,

  bookings: (query: BookingQuery) => ['bookings', query] as const,
  bookingTimeline: (id: Uuid) => ['bookings', id, 'timeline'] as const,

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
export const bookingWriteAffects = [
  ['bookings'],
  ['sessions'],
  ['dashboard'],
  ['alerts'],
] as const
