import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { getPublicSchedule } from '@/api/public'
import { ErrorState, Skeleton } from '@/components/ui/states'
import { keys } from '@/lib/query-keys'
import { formatDateLong, formatTime } from '@/lib/dates'
import { routes } from '@/lib/routes'
import { disciplineColor } from '@/lib/vocabulary'
import type { PublicSession } from '@/api/types'

/**
 * The timetable, for anyone.
 *
 * Not one of the ten goals. It exists because every other screen in this product
 * is behind a login, so somebody who has not been given an account cannot see
 * that any of it works — and a studio's timetable is the least private thing it
 * owns.
 *
 * It wears `.scheme-landing`, the same always-light palette as the landing page,
 * because this is the public face of the product rather than part of the tool. A
 * visitor should not be shown the dashboard's dark mode because of a preference
 * they set on a different site.
 *
 * Two decisions about what it shows. **Spaces left, not places booked** — that is
 * what the server sends, and it is what somebody deciding whether to come needs;
 * how full the studio's classes are is the studio's business. And **no booking
 * button**, because members do not have accounts (Decision 7). Pretending
 * otherwise would be the interface writing a cheque the system cannot cash.
 */
const DAYS_AHEAD = 14

export function PublicSchedulePage() {
  const schedule = useQuery({
    queryKey: keys.publicSchedule(DAYS_AHEAD),
    queryFn: () => getPublicSchedule(DAYS_AHEAD),
    // A public page reloaded by strangers on a free-tier instance. Five minutes of
    // staleness is invisible on a timetable and saves the instance a great deal.
    staleTime: 300_000,
  })

  const byDay = useMemo(() => groupByDay(schedule.data?.sessions ?? []), [schedule.data])

  return (
    <div className="scheme-landing min-h-screen">
      <header className="mx-auto flex max-w-[1000px] flex-wrap items-baseline justify-between gap-6 px-8 pb-10 pt-14 lg:px-12">
        <div>
          <Link
            to={routes.landing}
            className="display inline-block text-36 leading-none transition-colors duration-[120ms] hover:text-ink"
          >
            Mornington
          </Link>
          <p className="mt-3 max-w-[48ch] text-16 leading-[1.6] text-graphite">
            What is on over the next fortnight. Classes are booked at the front desk —
            call in or drop by.
          </p>
        </div>
        <Link
          to={routes.signIn}
          className="tracked text-11 text-graphite transition-colors duration-[120ms] hover:text-ink"
        >
          Staff sign in
        </Link>
      </header>

      <main className="mx-auto max-w-[1000px] px-8 pb-32 lg:px-12">
        {schedule.isPending && <Skeleton rows={6} />}
        {schedule.error && (
          <ErrorState error={schedule.error} onRetry={() => void schedule.refetch()} />
        )}

        {schedule.data && byDay.length === 0 && (
          <p className="border-t border-rule pt-10 text-16 text-graphite">
            Nothing is scheduled in the next fortnight. The timetable is usually published a
            week ahead.
          </p>
        )}

        {byDay.map(([date, sessions]) => (
          <section key={date} className="border-t border-rule pt-5 [&+&]:mt-10">
            <h2 className="text-12 font-medium text-graphite">{formatDateLong(date)}</h2>
            <ul className="mt-3">
              {sessions.map((session, index) => (
                <ClassRow key={`${date}-${index}`} session={session} />
              ))}
            </ul>
          </section>
        ))}

        {/* Said out loud rather than left as a short list. The server tells us when
            it capped the window; a page that silently stops is worse than one that
            explains why. */}
        {schedule.data?.truncated && (
          <p className="mt-10 text-12 text-graphite">
            Showing the first {schedule.data.sessions.length} classes. Call the studio for
            anything further ahead.
          </p>
        )}
      </main>
    </div>
  )
}

function ClassRow({ session }: { session: PublicSession }) {
  return (
    <li className="flex flex-wrap items-baseline gap-x-6 gap-y-2 border-b border-hairline py-4 last:border-b-0">
      <span
        aria-hidden="true"
        className="h-7 w-[3px] shrink-0 self-center rounded-full"
        style={{ background: disciplineColor(session.discipline) }}
      />

      <span className="condensed w-[74px] shrink-0 text-14 font-medium">
        {formatTime(session.start_time)}
      </span>

      <span className="min-w-0 flex-1">
        <span className="block text-16 font-medium">{session.class_title}</span>
        <span className="block text-12 text-graphite">
          {session.instructor_name} · {session.room_name} · {session.duration_min} min
        </span>
      </span>

      {/* The one piece of colour on the row, and it earns it: "full" is the only
          thing here that changes what a reader does next. */}
      <span className="shrink-0 text-12">
        {session.is_full ? (
          <span className="text-bad-ink">Full</span>
        ) : (
          <span className="text-graphite">
            {session.spots_remaining} {session.spots_remaining === 1 ? 'space' : 'spaces'} left
          </span>
        )}
      </span>
    </li>
  )
}

/** Group by date, preserving the server's ordering — it already sorted by start time. */
function groupByDay(sessions: PublicSession[]): [string, PublicSession[]][] {
  const days = new Map<string, PublicSession[]>()
  for (const session of sessions) {
    const existing = days.get(session.session_date)
    if (existing) existing.push(session)
    else days.set(session.session_date, [session])
  }
  return [...days.entries()]
}
