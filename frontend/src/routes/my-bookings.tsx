import { StatusChip } from '@/components/domain/chips'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useToast } from '@/components/ui/toast-context'
import { useCancelMyBooking, useMyBookings, useMyMembership } from '@/hooks/use-me'
import { formatDateLong, formatTimeRange } from '@/lib/dates'
import { routes } from '@/lib/routes'
import { Link } from 'react-router-dom'
import { PageHeader } from '@/layout/app-shell'
import type { MyBooking } from '@/api/types'

/**
 * What a member has booked, and whether they can book anything else.
 *
 * The member's home screen, and deliberately the whole of it: one list answering
 * "what am I going to" and "what did I go to", in that order, because a person
 * opening this is almost always asking the first.
 *
 * Every date and time here arrives already converted to the studio's wall clock,
 * and `session_has_passed` and `can_cancel` are the server's answers rather than
 * something worked out from a clock in the browser. That is what lets this screen
 * be correct on a phone in another timezone, which is where it will mostly be read.
 */
export function MyBookingsPage() {
  const membership = useMyMembership()
  const bookings = useMyBookings()

  if (bookings.isPending || membership.isPending) return <Skeleton rows={6} />
  if (bookings.error) {
    return <ErrorState error={bookings.error} onRetry={() => void bookings.refetch()} />
  }

  const rows = bookings.data ?? []
  const upcoming = rows.filter((row) => !row.session_has_passed)
  const past = rows.filter((row) => row.session_has_passed)

  return (
    <>
      <PageHeader
        title="My bookings"
        subtitle={
          upcoming.length === 0
            ? 'Nothing coming up yet.'
            : `${upcoming.length} ${upcoming.length === 1 ? 'class' : 'classes'} coming up.`
        }
      />
      {membership.data && <MembershipLine expired={membership.data.is_expired} />}

      <section className="flex flex-col gap-4">
        <h2 className="text-12 font-medium text-graphite">Coming up</h2>
        {upcoming.length === 0 ? (
          <EmptyState
            title="Nothing booked yet"
            action={
              <Link to={routes.myTimetable}>
                <Button size="sm" variant="primary">
                  Find a class
                </Button>
              </Link>
            }
          >
            Classes you book will appear here, with the time and the room.
          </EmptyState>
        ) : (
          <ul className="flex flex-col">
            {upcoming.map((row) => (
              <BookingRow key={row.id} booking={row} />
            ))}
          </ul>
        )}
      </section>

      {past.length > 0 && (
        <section className="flex flex-col gap-4">
          <h2 className="text-12 font-medium text-graphite">Already happened</h2>
          <ul className="flex flex-col">
            {past.map((row) => (
              <BookingRow key={row.id} booking={row} />
            ))}
          </ul>
        </section>
      )}
    </>
  )
}

/**
 * The one sentence a member needs about their membership.
 *
 * Shown only when it is expired, because "your membership is valid" is not news
 * and a banner that is always there stops being read. When it *is* expired this
 * is the explanation for a refusal they are about to meet, which is better than
 * meeting it first and working backwards.
 */
function MembershipLine({ expired }: { expired: boolean }) {
  if (!expired) return null
  return (
    <p className="mt-3 max-w-[56ch] text-14 leading-[1.6] text-bad-ink">
      Your membership has lapsed, so new bookings will be refused. Renew at the front desk
      and you can book again straight away — anything already booked is unaffected.
    </p>
  )
}

function BookingRow({ booking }: { booking: MyBooking }) {
  const cancel = useCancelMyBooking()
  const { notify } = useToast()

  return (
    <li className="flex flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-hairline py-4 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="text-16 font-medium">{booking.class_title}</p>
        <p className="mt-1 text-14 text-graphite">
          {formatDateLong(booking.session_date)} ·{' '}
          {formatTimeRange(booking.start_time, booking.duration_min)}
        </p>
        <p className="mt-0.5 text-12 text-graphite">
          {booking.instructor_name} · {booking.room_name}
        </p>
      </div>

      <StatusChip status={booking.status} position={booking.waitlist_position} />

      {booking.can_cancel && (
        <Button
          size="sm"
          disabled={cancel.isPending}
          onClick={() =>
            cancel.mutate(booking.id, {
              onSuccess: () =>
                notify('Booking cancelled', {
                  tone: 'good',
                  detail: `Your place on ${booking.class_title} has been given up.`,
                }),
            })
          }
        >
          {cancel.isPending ? 'Cancelling' : 'Cancel'}
        </Button>
      )}
    </li>
  )
}
