import { downloadFile, request } from './client'
import type {
  Booking,
  BookingEvent,
  LocalDate,
  BookingListItem,
  BookingSort,
  BookingStatus,
  BookingWithTimeline,
  CancelResult,
  Page,
  SortDirection,
  Uuid,
} from './types'

export interface BookingQuery {
  q?: string
  class_id?: Uuid
  session_id?: Uuid
  /** Sent as `status`; named apart here so it never collides with a row's status. */
  status?: BookingStatus
  /** Earliest class date, inclusive, in the studio's timezone. */
  date_from?: LocalDate
  /** Latest class date, inclusive — the whole of that day counts. */
  date_to?: LocalDate
  sort?: BookingSort
  direction?: SortDirection
  limit?: number
  offset?: number
}

/**
 * Find bookings (goal 6).
 *
 * `total` on the response counts the whole filtered set, not the page — goal 6
 * asks for the total number of matches, and a count of the rows returned would be
 * useless for that.
 *
 * The date range bounds the **class dates**, not when the bookings were taken.
 * That is the question a desk asks — "what is on next week, and who is coming" —
 * and it is the same thing those two words mean on the sessions endpoint.
 */
export function listBookings(query: BookingQuery = {}): Promise<Page<BookingListItem>> {
  return request<Page<BookingListItem>>('/bookings', { query: { ...query } })
}

/**
 * Book a member onto a session (goal 4).
 *
 * The response says which it was — `booked` or `waitlisted` — because the caller
 * does not decide. The server takes a row lock on the session, counts, and
 * assigns a place or a position in the queue; two clicks a millisecond apart
 * cannot both take the last spot.
 */
export function createBooking(
  sessionId: Uuid,
  memberId: Uuid,
  note?: string,
): Promise<Booking> {
  return request<Booking>('/bookings', {
    method: 'POST',
    body: { session_id: sessionId, member_id: memberId, note: note || null },
  })
}

/**
 * Cancel a booking.
 *
 * `promoted` is the reason this returns a result object rather than a booking: a
 * freed spot that was immediately refilled looks identical to one that was not
 * from the seat count alone, and the person at the desk needs to know whether to
 * say "you're in" to somebody.
 */
export function cancelBooking(bookingId: Uuid, note?: string): Promise<CancelResult> {
  return request<CancelResult>(`/bookings/${bookingId}/cancel`, {
    method: 'POST',
    body: { note: note || null },
  })
}

/** Attended or absent, once the session has passed (goals 4 and 9). */
export function settleBooking(
  bookingId: Uuid,
  attended: boolean,
  note?: string,
): Promise<Booking> {
  return request<Booking>(`/bookings/${bookingId}/settle`, {
    method: 'POST',
    body: { attended, note: note || null },
  })
}

/**
 * Add a note.
 *
 * Returns the new timeline entry rather than the booking, because that is what
 * was created: a note is an entry, never an edit, which is the whole point of
 * goal 9. Nothing about the booking itself has changed.
 */
export function addBookingNote(bookingId: Uuid, note: string): Promise<BookingEvent> {
  return request<BookingEvent>(`/bookings/${bookingId}/notes`, {
    method: 'POST',
    body: { note },
  })
}

export function getBookingTimeline(bookingId: Uuid): Promise<BookingWithTimeline> {
  return request<BookingWithTimeline>(`/bookings/${bookingId}/timeline`)
}

/** Goal 7's register, as a file the browser saves. */
export function downloadAttendanceCsv(sessionId: Uuid): Promise<void> {
  return downloadFile(`/sessions/${sessionId}/attendance.csv`, 'attendance.csv')
}
