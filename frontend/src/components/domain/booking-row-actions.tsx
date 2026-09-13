import { Link } from 'react-router-dom'
import type { CancelTarget } from './cancel-booking-dialog'
import { routes } from '@/lib/routes'
import type { BookingListItem } from '@/api/types'

/**
 * What you can do with a booking from the list it appears in.
 *
 * Both affordances here were once missing, and for opposite reasons. **Cancel**
 * existed only on a session's roster, so on the screen literally called Bookings
 * there was no way to do it. **History** was there all along as grey text with no
 * underline, which is to say it was there and nobody could tell.
 *
 * The cancel rule mirrors the server's exactly rather than a looser one: staff
 * only, and only while the booking is still active. Offering it on a settled
 * booking would be a button that 422s, which is worse than no button.
 */
export function BookingRowActions({
  booking,
  canCancel,
  onCancel,
}: {
  booking: BookingListItem
  canCancel: boolean
  onCancel: (target: CancelTarget) => void
}) {
  const active = booking.status === 'booked' || booking.status === 'waitlisted'

  return (
    <span className="inline-flex items-center gap-4">
      {canCancel && active && (
        <button
          type="button"
          onClick={() =>
            onCancel({
              bookingId: booking.id,
              memberName: booking.member_name,
              status: booking.status,
              className: booking.class_title,
              discipline: booking.discipline,
            })
          }
          className="text-12 text-graphite underline-offset-2 hover:text-bad-ink hover:underline"
        >
          Cancel
        </button>
      )}
      {/* Underlined always, not on hover: a grey word at the edge of a wide table
          reads as a label rather than as the way into goal 9's timeline. */}
      <Link
        to={routes.bookingHistory(booking.id)}
        className="text-12 text-graphite underline decoration-1 underline-offset-4 hover:text-ink"
      >
        History
      </Link>
    </span>
  )
}
