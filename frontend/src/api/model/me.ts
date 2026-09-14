// What a signed-in member sees of themselves.
//
// Separate from the studio models for the reason the server keeps them apart:
// these shapes carry no other member, no booking counts and no ids a member
// cannot act on. Mirroring that split here keeps the member screens unable to
// render a field the API would never send.

import type { BookingStatus, LocalDate, LocalTime, Instant, Uuid } from './common'

export interface MyMembership {
  full_name: string
  email: string
  membership_expiry: LocalDate
  /** Decided by the server in the studio's timezone, not by the browser. */
  is_expired: boolean
}

export interface MyBooking {
  id: Uuid
  status: BookingStatus
  booked_at: Instant

  session_date: LocalDate
  start_time: LocalTime
  duration_min: number

  class_title: string
  discipline: string
  instructor_name: string
  room_name: string

  session_has_passed: boolean
  /** 1-based place in the queue; null unless waitlisted. */
  waitlist_position: number | null
  /** Whether this member may still call it off. Decided server-side. */
  can_cancel: boolean
}

export interface BookableSession {
  id: Uuid

  session_date: LocalDate
  start_time: LocalTime
  duration_min: number

  class_title: string
  discipline: string
  description: string
  instructor_name: string
  room_name: string

  spots_remaining: number
  is_full: boolean
  /** This member's own active booking on it, or null. */
  my_status: BookingStatus | null
}
