// Read-only aggregates: the dashboard figures and the expiry alerts.

import type { BookingStatus, LocalDate, Uuid } from './common'

// --- dashboard (goal 8) -----------------------------------------------------

export interface HeadlineNumbers {
  sessions_today: number
  bookings_today: number
  no_shows_this_week: number
  members_waitlisted: number
}

export interface StatusCount {
  status: BookingStatus
  count: number
}

export interface ClassCount {
  class_id: Uuid
  class_title: string
  count: number
}

export interface WeekAttendance {
  week_start: LocalDate
  attended: number
  no_show: number
}

export interface Dashboard {
  headline: HeadlineNumbers
  by_status: StatusCount[]
  by_class: ClassCount[]
  attendance_by_week: WeekAttendance[]
  /** The studio's today, which is not always the viewer's. */
  as_of: LocalDate
  timezone: string
}
// --- alerts (goal 10) -------------------------------------------------------

export interface MembershipAlert {
  member_id: Uuid
  full_name: string
  email: string
  membership_expiry: LocalDate
  /** Negative once the date has passed. */
  days_remaining: number
  has_expired: boolean
}

export interface AlertFeed {
  items: MembershipAlert[]
  count: number
  window_days: number
}

// --- operations: room use and instructor pay ---------------------------------

export interface RoomUsage {
  room_id: Uuid
  room_name: string
  sessions: number
  minutes_booked: number
}

export interface InstructorPay {
  instructor_id: Uuid
  instructor_name: string
  sessions_taught: number
  minutes_taught: number
  /** Minor units — paise, pence, cents. Null means no rate has been set. */
  session_rate_minor: number | null
  /** Null when there is no rate, never zero. Those are different facts. */
  total_minor: number | null
}

export interface OperationsReport {
  starts: LocalDate
  ends: LocalDate
  rooms: RoomUsage[]
  instructors: InstructorPay[]
  /** Null when anybody who taught has no rate — an incomplete total is withheld. */
  payroll_total_minor: number | null
}
