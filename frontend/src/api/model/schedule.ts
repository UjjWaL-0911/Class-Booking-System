// The timetable: one class at one time in one room, and weekly generation.

import type { Instant, LocalDate, LocalTime, Uuid } from './common'

// --- the public schedule -----------------------------------------------------

/**
 * One class as a stranger sees it. Deliberately not a `Session`: the public
 * endpoint has its own response model on the server for the same reason this
 * type is separate here — nothing about the authenticated shape should be able
 * to reach an anonymous page by inheritance.
 */
export interface PublicSession {
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
}

export interface PublicSchedule {
  days_ahead: number
  starts: LocalDate
  ends: LocalDate
  /** The server capped the list. The page says so rather than implying a full window. */
  truncated: boolean
  sessions: PublicSession[]
}

// --- sessions ---------------------------------------------------------------

export interface Instructor {
  id: Uuid
  full_name: string
  email: string
}

export interface Session {
  id: Uuid
  class_id: Uuid
  class_title: string
  discipline: string

  session_date: LocalDate
  start_time: LocalTime
  starts_at: Instant
  ends_at: Instant

  room_id: Uuid
  room_name: string
  primary_instructor: Instructor
  co_instructors: Instructor[]

  duration_min: number
  capacity: number

  /**
   * Active bookings only. Once a class is over its bookings are settled, so this
   * falls to zero — which is correct for capacity and wrong for "how full was
   * it". Use `spotsTaken()` rather than reading this directly in a view.
   */
  booked_count: number
  waitlisted_count: number
  attended_count: number
  no_show_count: number
  seats_remaining: number

  version: number
}

export interface SessionCreate {
  class_id: Uuid
  session_date: LocalDate
  start_time: LocalTime
  primary_instructor_id: Uuid
  room_id: Uuid
  /** Omit to inherit the class default — `null` here means "inherit", not "none". */
  duration_min?: number | null
  capacity?: number | null
}

export type SessionUpdate = Partial<Omit<SessionCreate, 'class_id'>> & { version: number }
// --- recurrence (goal 7) ----------------------------------------------------

export type SkipReason = 'room_busy' | 'instructor_busy' | 'nonexistent_local_time'

export interface RecurrenceCreate {
  class_id: Uuid
  primary_instructor_id: Uuid
  room_id: Uuid
  start_time: LocalTime
  /** Python's convention: Monday is 0. */
  weekdays: number[]
  date_from: LocalDate
  date_to: LocalDate
  duration_min?: number | null
  capacity?: number | null
}

export interface SkippedOccurrence {
  session_date: LocalDate
  start_time: LocalTime
  reason: SkipReason
  detail: string
  conflicting_session_id: Uuid | null
}

export interface GenerationReport {
  requested: number
  created: Session[]
  skipped: SkippedOccurrence[]
}
