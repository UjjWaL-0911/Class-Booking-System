import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useToast } from '@/components/ui/toast-context'
import { useBookMyself, useBookableSessions, useMyMembership } from '@/hooks/use-me'
import { formatDateLong, formatTimeRange } from '@/lib/dates'
import { ordinal } from '@/lib/vocabulary'
import type { BookableSession } from '@/api/types'

/**
 * What is on, and one button per class.
 *
 * Grouped by day rather than listed flat, because somebody choosing a class is
 * choosing a *day* first — "what can I do on Thursday" is the question, and a
 * flat list makes them scan dates to answer it.
 *
 * Each row already knows whether this member is on it. That comes from the server
 * as `my_status` rather than being worked out here by cross-referencing the
 * bookings list, which would put a rule in the browser and let it drift the first
 * time a status was added.
 */
export function MySchedulePage() {
  const schedule = useBookableSessions()
  const membership = useMyMembership()

  if (schedule.isPending) return <Skeleton rows={6} />
  if (schedule.error) {
    return <ErrorState error={schedule.error} onRetry={() => void schedule.refetch()} />
  }

  const sessions = schedule.data ?? []
  const days = groupByDay(sessions)
  const lapsed = membership.data?.is_expired ?? false

  return (
    <div className="flex flex-col gap-12">
      <header>
        <h1 className="display text-32 leading-tight sm:text-36">Classes</h1>
        <p className="mt-3 max-w-[56ch] text-14 leading-[1.6] text-graphite">
          The next fortnight. Booking is instant — if a class is full you go on the waiting
          list, and you move up automatically when somebody cancels.
        </p>
        {lapsed && (
          <p className="mt-3 max-w-[56ch] text-14 leading-[1.6] text-bad-ink">
            Your membership has lapsed, so bookings will be refused until you renew at the
            front desk.
          </p>
        )}
      </header>

      {days.length === 0 ? (
        <EmptyState title="Nothing scheduled">
          There are no classes on the timetable for the next two weeks.
        </EmptyState>
      ) : (
        days.map(([date, rows]) => (
          <section key={date} className="flex flex-col gap-3">
            <h2 className="text-12 font-medium text-graphite">{formatDateLong(date)}</h2>
            <ul className="flex flex-col">
              {rows.map((session) => (
                <SessionRow key={session.id} session={session} />
              ))}
            </ul>
          </section>
        ))
      )}
    </div>
  )
}

function SessionRow({ session }: { session: BookableSession }) {
  const book = useBookMyself()
  const { notify } = useToast()

  return (
    <li className="flex flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-hairline py-4 last:border-b-0">
      <div className="min-w-0 flex-1">
        <p className="text-16 font-medium">{session.class_title}</p>
        <p className="mt-1 text-14 text-graphite">
          {formatTimeRange(session.start_time, session.duration_min)} · {session.instructor_name}{' '}
          · {session.room_name}
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
                    : `You are number ${booking.waitlist_position} in the queue. You move up automatically if somebody cancels.`,
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

/**
 * Places left, never places taken.
 *
 * What a person choosing a class needs, and it says nothing about how the
 * studio's business is going — the same line the public timetable draws.
 */
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
 * A member already on a class is shown their standing rather than a disabled
 * button: "you are on the waiting list" answers the question, where a greyed-out
 * "Book" leaves them wondering whether it failed.
 *
 * **And the queue position comes with it.** This screen first said only "on the
 * waiting list" while the member's own list said "Waiting list · 1st", which is
 * two answers to one question — and the timetable is where somebody is *deciding*
 * whether to wait, so it is the screen that most needs the number.
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

/** Sessions bucketed by their local date, in the order the server sent them. */
function groupByDay(sessions: BookableSession[]): [string, BookableSession[]][] {
  const days = new Map<string, BookableSession[]>()
  for (const session of sessions) {
    const bucket = days.get(session.session_date)
    if (bucket) bucket.push(session)
    else days.set(session.session_date, [session])
  }
  return [...days.entries()]
}
