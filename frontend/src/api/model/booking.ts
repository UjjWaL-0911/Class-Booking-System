// Bookings, their lifecycle, and the immutable record of it.

import type { BookingEventType, BookingStatus, Instant, LocalDate, LocalTime, Uuid } from './common'

// --- bookings ---------------------------------------------------------------

export interface MemberSummary {
  id: Uuid
  full_name: string
  email: string
  membership_expiry: LocalDate
}

export interface Booking {
  id: Uuid
  session_id: Uuid
  status: BookingStatus
  booked_at: Instant
  cancelled_at: Instant | null
  settled_at: Instant | null
  member: MemberSummary
}

export interface BookingEvent {
  id: number
  event_type: BookingEventType
  old_status: BookingStatus | null
  new_status: BookingStatus | null
  note: string | null
  /** Null exactly when `is_system` is true. Nobody did it; the system did. */
  actor_name: string | null
  is_system: boolean
  occurred_at: Instant
}

export interface BookingWithTimeline extends Booking {
  events: BookingEvent[]
  /** 1-based place in the queue. Null unless this booking is waitlisted. */
  waitlist_position: number | null
}

/** Cancelling can promote the next person in line, so the response says whether it did. */
export interface CancelResult {
  booking: Booking
  promoted: Booking | null
}

export interface BookingListItem {
  id: Uuid
  status: BookingStatus
  booked_at: Instant

  member_id: Uuid
  member_name: string
  member_email: string

  session_id: Uuid
  session_starts_at: Instant
  session_date: LocalDate
  session_start_time: LocalTime

  class_id: Uuid
  class_title: string
  /** So a row can say a mat or a bike opened up rather than a generic "spot". */
  discipline: string

  /** A waitlisted booking on a session that has already happened stays waitlisted. */
  session_has_passed: boolean

  /** 1-based place in the queue. Null unless this booking is waitlisted. */
  waitlist_position: number | null
}

// --- booking a whole term ----------------------------------------------------

export type BookingSkipReason =
  | 'already_booked'
  | 'membership_expired'
  | 'session_started'
  | 'class_archived'
  | 'refused'

export interface TermBookingCreate {
  member_id: Uuid
  class_id: Uuid
  date_from: LocalDate
  date_to: LocalDate
  /** Monday is 0. Omitted means every session of the class in the range. */
  weekdays?: number[] | null
  note?: string | null
}

export interface TermBookingOutcome {
  session_id: Uuid
  session_date: LocalDate
  start_time: LocalTime
  booking_id: Uuid | null
  waitlisted: boolean
  reason: BookingSkipReason | null
  detail: string | null
}

/** Three outcomes, not two: a full session waitlists, which is a result not a skip. */
export interface TermBookingReport {
  requested: number
  booked: TermBookingOutcome[]
  waitlisted: TermBookingOutcome[]
  skipped: TermBookingOutcome[]
}

export type BookingSort = 'booked_at' | 'status' | 'session'
export type SortDirection = 'asc' | 'desc'
