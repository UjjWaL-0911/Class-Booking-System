import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import type { HeadlineNumbers, WeekAttendance } from '@/api/types'
import { routes } from '@/lib/routes'

/**
 * Goal 8's four figures, as cards.
 *
 * The thing that makes a stat card worth its border is whether it says anything
 * the number alone does not. Four boxes each holding one digit is four borders
 * buying nothing, so every card here carries a second line that the figure cannot
 * tell you on its own:
 *
 *   - classes today   -> which one is next, and when
 *   - bookings taken  -> whose bookings these are, since the server scopes the
 *                        figure to the viewer and an instructor's number is not
 *                        the studio's
 *   - absences        -> the same week last week, which is the only way to know
 *                        whether seven is a bad week or a normal one
 *   - waiting         -> what happens to them next
 *
 * And each card is a link to the rows behind it, so a number somebody doesn't
 * believe is one click from the list that produced it.
 *
 * Colour follows the same rule as everywhere else: it means something or it is
 * absent. The two operational counts are always ink. The two that ask for
 * attention take their status colour only when they are non-zero — a week with no
 * absences is not a red week, it is a quiet one.
 */
export function HeadlineCards({
  headline,
  weeks,
  scope,
  nextUp,
}: {
  headline: HeadlineNumbers
  weeks: WeekAttendance[]
  /** Whose figures these are. The server decides; the card says so. */
  scope: 'studio' | 'yours'
  /** What is on next today, where the caller knows. */
  nextUp?: string
}) {
  const { sessions_today, bookings_today, no_shows_this_week, members_waitlisted } = headline

  return (
    <div className="grid grid-cols-1 gap-x-10 gap-y-8 sm:grid-cols-2 xl:grid-cols-4">
      <Card
        label="Classes today"
        value={sessions_today}
        to={routes.timetable}
        detail={
          nextUp ??
          (sessions_today === 0 ? 'Nothing on the timetable today' : 'On the timetable today')
        }
      />

      <Card
        label="Bookings taken today"
        value={bookings_today}
        to={routes.bookings}
        detail={scope === 'studio' ? 'Across the whole studio' : 'On the classes you teach'}
      />

      <Card
        label="Absences this week"
        value={no_shows_this_week}
        to={routes.bookingsWithStatus('no_show')}
        tone={no_shows_this_week > 0 ? 'bad' : 'quiet'}
        detail={lastWeekPhrase(weeks)}
      />

      <Card
        label="Waiting for a spot"
        value={members_waitlisted}
        to={routes.bookingsWithStatus('waitlisted')}
        tone={members_waitlisted > 0 ? 'wait' : 'quiet'}
        detail={
          members_waitlisted === 0
            ? 'Nothing is full at the moment'
            : 'Each takes the next spot that opens'
        }
      />
    </div>
  )
}

const TONE = {
  ink: 'text-ink',
  bad: 'text-bad-ink',
  wait: 'text-wait-ink',
  // A zero that nobody needs to act on. Graphite rather than ink, so the cards
  // that do want attention are the ones the eye lands on.
  quiet: 'text-graphite',
} as const

function Card({
  label,
  value,
  detail,
  to,
  tone = 'ink',
}: {
  label: string
  value: number
  detail: string
  to: string
  tone?: keyof typeof TONE
}) {
  return (
    <Link
      to={to}
      className={cn(
        // A rule above rather than a box around. They are still four distinct
        // units — which is what a card is for — without four outlines competing
        // on a page that has no other outlines left.
        'group flex min-h-[132px] flex-col gap-3 border-t border-rule pr-6 pt-5',
        'transition-colors duration-[120ms] hover:border-ink',
      )}
    >
      <span className="tracked text-11 font-medium text-graphite">{label}</span>

      <span
        className={cn('condensed text-44 font-medium tracking-[-0.02em]', TONE[tone])}
        style={{ lineHeight: 1 }}
      >
        {value}
      </span>

      {/* Pushed to the bottom so the figures sit on one line across all four
          cards however long the labels wrap. */}
      <span className="mt-auto text-12 text-graphite text-pretty">{detail}</span>
    </Link>
  )
}

/**
 * The same week, last week.
 *
 * Safe to compare: the headline figure and the chart's buckets are both counted
 * on the session's local date and both use a Monday-start week, so these are the
 * same measurement one week apart rather than two definitions that happen to sit
 * near each other.
 */
function lastWeekPhrase(weeks: WeekAttendance[]): string {
  const previous = weeks.at(-2)
  if (previous === undefined) return 'No week to compare against yet'
  if (previous.no_show === 0) return 'None at all last week'
  return `${previous.no_show} last week`
}
