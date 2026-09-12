/**
 * The wire format, mirrored from the backend's Pydantic models.
 *
 * Written by hand rather than generated. That is a deliberate trade: a generator
 * would keep these in step automatically, but it would also import forty
 * endpoint signatures the interface never calls and bury the two distinctions
 * that actually matter here — which are documented below, where they belong.
 *
 * Dates and times arrive as strings, and the type names say which kind:
 *
 *   `LocalDate`  "2026-09-11"          a calendar date in the studio's timezone
 *   `LocalTime`  "18:00:00"            a wall-clock time in the studio's timezone
 *   `Instant`    "2026-09-11T17:00:00Z" an absolute moment, UTC
 *
 * Sessions carry both representations. Display the local pair: it is already the
 * studio's wall clock, so rendering it needs no timezone at all and cannot be
 * corrupted by the viewer's own. Compare and sort on the instants. Getting this
 * backwards is how a studio in London shows a 7am class to a member in Mumbai as
 * a 12:30pm one.
 */

export type LocalDate = string
export type LocalTime = string
export type Instant = string
export type Uuid = string

export type UserRole = 'staff' | 'instructor'

export type BookingStatus = 'booked' | 'waitlisted' | 'cancelled' | 'attended' | 'no_show'

export type BookingEventType = 'created' | 'status_changed' | 'note_added'

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}
