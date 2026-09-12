import { Link } from 'react-router-dom'
import { ExpiryChip, StatusChip } from './chips'
import type { CancelTarget } from './cancel-booking-dialog'
import { Button } from '@/components/ui/button'
import { PersonCell, Td, Tr } from '@/components/ui/table'
import { useToast } from '@/components/ui/toast-context'
import { useIsStaff } from '@/hooks/use-auth'
import { useSettleBooking } from '@/hooks/use-bookings'
import { useStudio } from '@/studio/studio-context'
import { daysBetween, formatDayMonth } from '@/lib/dates'
import { hasFinished } from '@/lib/occupancy'
import { ordinal } from '@/lib/vocabulary'
import type { BookingListItem, Session } from '@/api/types'
import { routes } from '@/lib/routes'

/**
 * The two kinds of row a session's roster has.
 *
 * They look similar and mean different things, which is why they are separate
 * components rather than one with a flag: a roster row is a register entry that
 * gains attendance buttons once the class is over, and a waiting row is a queue
 * position that can never gain them. Merging them would put a branch inside every
 * cell.
 */
export function RosterRow({
  booking,
  index,
  session,
  justPromoted,
  onCancel,
}: {
  booking: BookingListItem
  index: number
  session: Session
  justPromoted: boolean
  onCancel: (target: CancelTarget) => void
}) {
  const { today } = useStudio()
  const { notify } = useToast()
  const settle = useSettleBooking()
  const isStaff = useIsStaff()

  const daysRemaining = daysBetween(today, booking.session_date)
  const finished = hasFinished(session)

  return (
    <Tr justPromoted={justPromoted}>
      <Td className="pr-2 text-right text-11 text-graphite">{index + 1}</Td>
      <Td>
        <Link to={routes.bookingHistory(booking.id)} className="hover:text-ink hover:underline">
          <PersonCell name={booking.member_name} />
        </Link>
      </Td>
      <Td>
        <ExpiryChip daysRemaining={daysRemaining} />
      </Td>
      <Td className="text-graphite">{formatDayMonth(booking.session_date)}</Td>
      <Td>
        {booking.status !== 'booked' ? (
          <StatusChip status={booking.status} />
        ) : finished ? (
          /* Attendance only once the class has finished — goal 4's rule, and the
             server enforces it. Buttons that appear before then would be buttons
             that fail. */
          <div className="flex gap-1.5">
            <Button
              size="sm"
              disabled={settle.isPending}
              onClick={() =>
                settle.mutate(
                  { bookingId: booking.id, attended: true },
                  { onSuccess: () => notify('Attended', { tone: 'good', detail: booking.member_name }) },
                )
              }
            >
              Attended
            </Button>
            <Button
              size="sm"
              disabled={settle.isPending}
              onClick={() =>
                settle.mutate(
                  { bookingId: booking.id, attended: false },
                  { onSuccess: () => notify('Marked absent', { tone: 'bad', detail: booking.member_name }) },
                )
              }
            >
              Absent
            </Button>
          </div>
        ) : isStaff ? (
          <button
            type="button"
            onClick={() =>
              onCancel({
                bookingId: booking.id,
                memberName: booking.member_name,
                status: booking.status,
                className: session.class_title,
                discipline: session.discipline,
              })
            }
            className="text-12 text-graphite underline-offset-2 hover:text-bad-ink hover:underline"
          >
            Cancel
          </button>
        ) : (
          <StatusChip status={booking.status} />
        )}
      </Td>
    </Tr>
  )
}

export function WaitingRow({
  booking,
  position,
  session,
  onCancel,
}: {
  booking: BookingListItem
  position: number
  session: Session
  onCancel: (target: CancelTarget) => void
}) {
  const { today } = useStudio()
  const isStaff = useIsStaff()
  const daysRemaining = daysBetween(today, booking.session_date)
  const lapsed = daysRemaining < 0

  return (
    <Tr>
      <Td className="w-10 pr-2 text-right text-11 text-graphite">{ordinal(position)}</Td>
      <Td className="w-[30%]">
        <Link to={routes.bookingHistory(booking.id)} className="hover:text-ink hover:underline">
          <PersonCell name={booking.member_name} />
        </Link>
        {lapsed && (
          <span className="text-11 text-graphite">
            Will be passed over while the membership is expired
          </span>
        )}
      </Td>
      <Td className="w-[22%]">
        <ExpiryChip daysRemaining={daysRemaining} />
      </Td>
      <Td className="w-[14%] text-graphite">{formatDayMonth(booking.session_date)}</Td>
      <Td>
        {isStaff && (
          <button
            type="button"
            onClick={() =>
              onCancel({
                bookingId: booking.id,
                memberName: booking.member_name,
                status: booking.status,
                className: session.class_title,
                discipline: session.discipline,
              })
            }
            className="text-12 text-graphite underline-offset-2 hover:text-bad-ink hover:underline"
          >
            Take off the list
          </button>
        )}
      </Td>
    </Tr>
  )
}
