import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast-context'
import { useBookMyself } from '@/hooks/use-me'
import { formatDateLong, formatTimeRange } from '@/lib/dates'
import { ordinal } from '@/lib/vocabulary'
import type { BookableSession } from '@/api/types'

/**
 * One class on the timetable, with the one thing a member can do about it.
 *
 * Split out of the timetable page so that file reads as what it is — search,
 * filter, order, and the shape of the list — rather than interleaving those with
 * the anatomy of a row.
 *
 * The booking mutation lives on the row rather than the page, so a pending button
 * belongs to the class being booked instead of disabling the whole list.
 */
export function SessionList({ rows, withDate = false }: { rows: BookableSession[]; withDate?: boolean }) {
  return (
    <ul className="flex flex-col">
      {rows.map((session) => (
        <SessionRow key={session.id} session={session} withDate={withDate} />
      ))}
    </ul>
  )
}

function SessionRow({ session, withDate }: { session: BookableSession; withDate: boolean }) {
  const book = useBookMyself()
  const { notify } = useToast()

  return (
    <li className="flex flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-hairline py-4 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="text-16 font-medium">{session.class_title}</p>
        <p className="mt-1 text-14 text-graphite">
          {withDate && `${formatDateLong(session.session_date)} · `}
          {formatTimeRange(session.start_time, session.duration_min)} · {session.instructor_name} ·{' '}
          {session.room_name}
        </p>
      </div>

      <Seats session={session} />

      <Action
        session={session}
        pending={book.isPending}
        onBook={() =>
          book.mutate(session.id, {
            onSuccess: (booking) =>
              notify(booking.status === 'booked' ? 'Booked' : 'On the waiting list', {
                tone: 'good',
                detail:
                  booking.status === 'booked'
                    ? `Your place on ${session.class_title} is held.`
                    : `You are ${ordinal(booking.waitlist_position ?? 1)} in the queue, and move up automatically if somebody cancels.`,
              }),
            onError: (error) =>
              notify('Could not book that', {
                tone: 'bad',
                detail:
                  error instanceof ApiError ? error.message : 'Please try again in a moment.',
              }),
          })
        }
      />
    </li>
  )
}

/** Places left, never places taken — the line the public timetable also draws. */
function Seats({ session }: { session: BookableSession }) {
  if (session.is_full) {
    return <span className="text-12 text-wait-ink">Full — waiting list</span>
  }
  return (
    <span className="text-12 text-graphite">
      {session.spots_remaining} {session.spots_remaining === 1 ? 'place' : 'places'} left
    </span>
  )
}

/**
 * One button, or where you already stand.
 *
 * Somebody already on a class is shown their standing rather than a disabled
 * button: "on the waiting list, 2nd" answers the question, where a greyed-out
 * Book leaves them wondering whether it failed.
 */
function Action({
  session,
  pending,
  onBook,
}: {
  session: BookableSession
  pending: boolean
  onBook: () => void
}) {
  if (session.my_status === 'booked') {
    return <span className="text-12 font-medium text-good-ink">You are booked</span>
  }
  if (session.my_status === 'waitlisted') {
    return (
      <span className="text-12 font-medium text-wait-ink">
        {session.my_waitlist_position === null
          ? 'On the waiting list'
          : `On the waiting list · ${ordinal(session.my_waitlist_position)}`}
      </span>
    )
  }
  return (
    <Button size="sm" variant="primary" disabled={pending} onClick={onBook}>
      {pending ? 'Booking' : session.is_full ? 'Join the list' : 'Book'}
    </Button>
  )
}
