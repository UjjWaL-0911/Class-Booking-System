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
}

export type BookingSort = 'booked_at' | 'status' | 'session'
export type SortDirection = 'asc' | 'desc'
