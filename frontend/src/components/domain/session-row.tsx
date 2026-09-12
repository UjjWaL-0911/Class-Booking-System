import { Link } from 'react-router-dom'
import { Occupancy } from './occupancy-mark'
import { formatDateShort, formatTime } from '@/lib/dates'
import { routes } from '@/lib/routes'
import { disciplineColor } from '@/lib/vocabulary'
import type { Session } from '@/api/types'

/**
 * One class, as it appears on Today and on the Timetable.
 *
 * It used to be a bordered card, and a list of them was a stack of boxes with the
 * information trapped inside each. Now it is a row: a hairline underneath, and
 * nothing else. What tells you where one class ends and the next begins is the
 * rule and the space, which is all a list has ever needed.
 *
 * The discipline tint survived the change as a short stroke rather than a left
 * edge — an edge only reads as an edge when there is a box for it to be the edge
 * *of*. At this size it still groups a week's yoga classes by eye without asking
 * for attention.
 *
 * The whole row is the link. A row with a link in its title and a button on the
 * right makes somebody choose between two ways to the same screen, and puts two
 * targets where the hand wants one.
 */
export function SessionRow({ session, showDate = false }: { session: Session; showDate?: boolean }) {
  const others = session.co_instructors.map((person) => person.full_name)

  return (
    <Link
      to={routes.session(session.id)}
      className="group flex items-center gap-7 border-b border-hairline py-5 transition-colors duration-[120ms] last:border-b-0 hover:bg-row"
    >
      <span
        className="h-9 w-[3px] shrink-0 rounded-full"
        style={{ background: disciplineColor(session.discipline) }}
        aria-hidden="true"
      />

      <div className="w-[76px] shrink-0">
        <p className="condensed text-21 font-medium tracking-[0.01em]">
          {formatTime(session.start_time)}
        </p>
        <p className="mt-0.5 text-11 text-graphite">
          {showDate ? formatDateShort(session.session_date) : `${session.duration_min} min`}
        </p>
      </div>

      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <p className="text-16 font-medium tracking-[-0.01em]">{session.class_title}</p>
        <div className="flex flex-wrap gap-x-5 gap-y-0.5 text-12 text-graphite">
          <span>{session.room_name}</span>
          <span>{session.primary_instructor.full_name}</span>
          {others.length > 0 && <span>with {others.join(' and ')}</span>}
        </div>
      </div>

      <Occupancy session={session} className="w-[210px] shrink-0" />

      <svg
        width="12"
        height="12"
        viewBox="0 0 12 12"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="shrink-0 text-mute transition-colors duration-[120ms] group-hover:text-graphite"
        aria-hidden="true"
      >
        <polyline points="4.5,2 8.5,6 4.5,10" />
      </svg>
    </Link>
  )
}
