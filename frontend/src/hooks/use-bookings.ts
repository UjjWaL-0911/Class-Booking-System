import { useMutation, useQuery, useQueryClient, type QueryClient } from '@tanstack/react-query'
import {
  addBookingNote,
  cancelBooking,
  createBooking,
  getBookingTimeline,
  listBookings,
  settleBooking,
  type BookingQuery,
} from '@/api/bookings'
import { bookingWriteAffects, keys } from '@/lib/query-keys'
import type { Uuid } from '@/api/types'

function invalidateAfterBookingWrite(client: QueryClient): void {
  for (const key of bookingWriteAffects) {
    void client.invalidateQueries({ queryKey: key })
  }
}

export function useBookings(query: BookingQuery) {
  return useQuery({
    queryKey: keys.bookings(query),
    queryFn: () => listBookings(query),
    // Keeps the previous page on screen while the next one loads, so paging
    // through a list does not blank the table on every click.
    placeholderData: (previous) => previous,
  })
}

/** Every booking on one session — the roster and the waiting list together. */
export function useRoster(sessionId: Uuid) {
  return useQuery({
    queryKey: keys.roster(sessionId),
    queryFn: () =>
      listBookings({
        session_id: sessionId,
        // A full class plus its waiting list can exceed the default page, and a
        // roster that silently stops at fifty is a roster somebody gets marked
        // absent from.
        limit: 200,
        sort: 'booked_at',
        direction: 'asc',
      }),
  })
}

export function useBookingTimeline(bookingId: Uuid) {
  return useQuery({
    queryKey: keys.bookingTimeline(bookingId),
    queryFn: () => getBookingTimeline(bookingId),
  })
}

/**
 * Take a booking (goal 4).
 *
 * No optimistic update, deliberately. The server decides whether this is a place
 * or a queue position, and it decides it under a row lock while counting the
 * other bookings. A client guess would be right most of the time and wrong
 * exactly when it matters — on the last spot, with two people at two screens —
 * and the wrong guess is the one that tells somebody they are in when they are
 * not.
 */
export function useCreateBooking() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      sessionId,
      memberId,
      note,
    }: {
      sessionId: Uuid
      memberId: Uuid
      note?: string
    }) => createBooking(sessionId, memberId, note),
    onSuccess: () => invalidateAfterBookingWrite(client),
  })
}

/** Cancelling may promote the next eligible person; the result says whether it did. */
export function useCancelBooking() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ bookingId, note }: { bookingId: Uuid; note?: string }) =>
      cancelBooking(bookingId, note),
    onSuccess: () => invalidateAfterBookingWrite(client),
  })
}

export function useSettleBooking() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({
      bookingId,
      attended,
      note,
    }: {
      bookingId: Uuid
      attended: boolean
      note?: string
    }) => settleBooking(bookingId, attended, note),
    onSuccess: () => invalidateAfterBookingWrite(client),
  })
}

export function useAddBookingNote() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ bookingId, note }: { bookingId: Uuid; note: string }) =>
      addBookingNote(bookingId, note),
    onSuccess: (_booking, { bookingId }) => {
      void client.invalidateQueries({ queryKey: keys.bookingTimeline(bookingId) })
      void client.invalidateQueries({ queryKey: ['bookings'] })
    },
  })
}
