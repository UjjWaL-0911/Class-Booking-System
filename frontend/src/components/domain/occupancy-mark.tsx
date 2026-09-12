import { cn } from '@/lib/cn'
import { hasFinished, spotsTaken } from '@/lib/occupancy'
import { spotNoun } from '@/lib/vocabulary'
import type { Session } from '@/api/types'

/**
 * How full a class is, counted rather than measured.
 *
 * This is the one place this interface raises its voice, and the reason it works
 * is that a studio room is *countable*: eighteen mats, twelve bikes, eight
 * reformers. One filled mark per taken spot and one ring per free one is not a
 * decoration of the number — it is the number, in the same form the instructor
 * sees when she looks at the floor. "Two bikes free" is a glance; "83%" is
 * arithmetic.
 *
 * Which is also why it is not a progress bar. A bar says *how much of the way
 * there* — a fraction of an abstract whole — and invites a reader to estimate
 * where a studio needs them to count. The marks refuse to be estimated.
 *
 * Above `MAX_MARKS` spots the marks stop earning their place: nobody counts
 * thirty-one dots, and a row of them is a texture rather than a quantity. Past
 * that point the component shows the figures alone. Degrading to the number is
 * honest; degrading to a bar would be the thing this component exists to avoid.
 */
const MAX_MARKS = 24

type Size = 'sm' | 'lg'

const DOT: Record<Size, string> = {
  sm: 'size-2',
  lg: 'size-[11px]',
}

const GAP: Record<Size, string> = {
  sm: 'gap-1',
  lg: 'gap-1.5',
}

/** The marks alone, for a caller that prints its own figures. */
export function OccupancyMark({
  taken,
  capacity,
  size = 'sm',
  className,
}: {
  taken: number
  capacity: number
  size?: Size
  className?: string
}) {
  if (capacity > MAX_MARKS) return null

  const filled = Math.min(taken, capacity)
  return (
    <div
      className={cn('flex flex-wrap items-center', GAP[size], className)}
      // The marks are a picture of the two numbers beside them, so they are
      // hidden from assistive technology rather than read out as eighteen
      // anonymous list items.
      aria-hidden="true"
    >
      {Array.from({ length: capacity }, (_, index) => (
        <span
          key={index}
          className={cn(
            'shrink-0 rounded-full',
            DOT[size],
            index < filled ? 'bg-ink' : 'border border-mute',
          )}
        />
      ))}
    </div>
  )
}

/**
 * The marks and the figures together — the form used in lists.
 *
 * Reads differently depending on whether the class is still ahead, because the
 * question is different. Before: how many spots are left, and is anyone queueing.
 * After: who turned up. Showing "2 waiting" beside an empty room for a class that
 * ran full and finished is the bug this component was rewritten to fix.
 */
export function Occupancy({
  session,
  size = 'sm',
  className,
}: {
  session: Session
  size?: Size
  className?: string
}) {
  const taken = spotsTaken(session)
  const finished = hasFinished(session)
  const free = Math.max(session.capacity - taken, 0)

  return (
    <div className={cn('flex flex-col items-end gap-1.5', className)}>
      <OccupancyMark taken={taken} capacity={session.capacity} size={size} />
      <div className="flex items-center gap-2.5 text-12">
        <span className="font-medium text-ink">
          {taken} of {session.capacity}
        </span>
        <Aside session={session} finished={finished} free={free} />
      </div>
    </div>
  )
}

function Aside({
  session,
  finished,
  free,
}: {
  session: Session
  finished: boolean
  free: number
}) {
  const divider = <span className="h-3 w-px bg-rule" />

  if (finished) {
    // Still-active bookings on a finished class are people nobody has marked yet.
    // That is the actionable fact, so it wins over the attendance split.
    if (session.booked_count > 0) {
      return (
        <>
          {divider}
          <span className="text-wait-ink">{session.booked_count} still to mark</span>
        </>
      )
    }
    if (session.no_show_count > 0) {
      return (
        <>
          {divider}
          <span className="text-bad-ink">
            {session.no_show_count} absent
          </span>
        </>
      )
    }
    if (session.attended_count > 0) {
      return (
        <>
          {divider}
          <span className="text-good-ink">all attended</span>
        </>
      )
    }
    return null
  }

  if (session.waitlisted_count > 0) {
    return (
      <>
        {divider}
        <span className="text-wait-ink">{session.waitlisted_count} waiting</span>
      </>
    )
  }

  if (free > 0) {
    return (
      <>
        {divider}
        <span className="text-graphite">
          {free} {spotNoun(session.discipline, free !== 1)} free
        </span>
      </>
    )
  }

  return null
}
