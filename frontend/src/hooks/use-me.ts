import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  bookMyself,
  cancelMyBooking,
  getMyMembership,
  listBookableSessions,
  listMyBookings,
  listOfferedClasses,
} from '@/api/me'
import { keys, memberWriteAffects } from '@/lib/query-keys'
import type { Uuid } from '@/api/types'

/** How far ahead a member can browse. The server caps it at 31. */
export const SCHEDULE_DAYS = 14

export function useMyMembership() {
  return useQuery({
    queryKey: keys.myMembership,
    queryFn: getMyMembership,
    // A membership expiry changes when staff edit it, which is rare and happens
    // elsewhere. Long enough to stop every screen refetching it, short enough
    // that a renewal shows up while the member is still looking.
    staleTime: 300_000,
  })
}

export function useMyBookings() {
  return useQuery({ queryKey: keys.myBookings, queryFn: listMyBookings })
}

/**
 * What the studio offers.
 *
 * A long `staleTime`: a studio's catalogue changes when somebody adds a class,
 * which is a rare thing done elsewhere. Refetching it on every visit to the
 * timetable would be a request that almost never returns anything new.
 */
export function useOfferedClasses() {
  return useQuery({
    queryKey: keys.myClasses,
    queryFn: listOfferedClasses,
    staleTime: 600_000,
  })
}

export function useBookableSessions(days = SCHEDULE_DAYS) {
  return useQuery({
    queryKey: keys.mySchedule(days),
    queryFn: () => listBookableSessions(days),
  })
}

/**
 * Book, or cancel.
 *
 * Both invalidate the schedule as well as the bookings list, and that is the
 * point rather than housekeeping: every row of the schedule carries this
 * member's own status and the seats left on it, so a booking changes the list
 * they came from. Leaving it stale would show a "Book" button on a class they
 * are already on.
 */
function useMemberWrite<T>(fn: (id: Uuid) => Promise<T>) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      for (const key of memberWriteAffects) {
        void client.invalidateQueries({ queryKey: key })
      }
    },
  })
}

export function useBookMyself() {
  return useMemberWrite(bookMyself)
}

export function useCancelMyBooking() {
  return useMemberWrite(cancelMyBooking)
}
