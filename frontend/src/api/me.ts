import { request } from './client'
import type { BookableSession, MyBooking, MyMembership, Uuid } from './types'

/**
 * The member's own surface.
 *
 * **None of these take a member id.** The server resolves the member from the
 * credential, so there is nothing here for the client to pass and nothing for it
 * to get wrong — which is also why none of these functions need to know who is
 * signed in.
 */
export function getMyMembership(): Promise<MyMembership> {
  return request<MyMembership>('/me/membership')
}

export function listMyBookings(): Promise<MyBooking[]> {
  return request<MyBooking[]>('/me/bookings')
}

export function listBookableSessions(days: number): Promise<BookableSession[]> {
  return request<BookableSession[]>(`/me/schedule?days=${days}`)
}

export function bookMyself(sessionId: Uuid): Promise<MyBooking> {
  return request<MyBooking>('/me/bookings', {
    method: 'POST',
    body: { session_id: sessionId },
  })
}

export function cancelMyBooking(bookingId: Uuid): Promise<MyBooking> {
  return request<MyBooking>(`/me/bookings/${bookingId}/cancel`, {
    method: 'POST',
    body: {},
  })
}
