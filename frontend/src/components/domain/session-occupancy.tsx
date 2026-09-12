import { OccupancyMark } from './occupancy-mark'
import { Panel } from '@/components/ui/panel'
import { hasFinished, spotsTaken, unmarkedCount } from '@/lib/occupancy'
import { disciplineColor, spotNoun } from '@/lib/vocabulary'
import type { Session } from '@/api/types'

/**
 * The largest thing on the session screen, and the only place this interface
 * uses the top of the type scale.
 *
 * Somebody reads this standing in the doorway of the room, so the count deserves
 * the space. Which figures appear depends on whether the class is still ahead:
 * before it runs, how many spots are left and who is queueing; after, who turned
 * up and whether anybody is still unmarked. A finished class showing "2 waiting"
 * beside an empty room was a real bug here — the view was reading the count of
 * *active* bookings, which settling empties. See lib/occupancy.
 */
export function SessionOccupancy({ session }: { session: Session }) {
  const noun = spotNoun(session.discipline)
  const taken = spotsTaken(session)
  const free = Math.max(session.capacity - taken, 0)
  const finished = hasFinished(session)
  const unmarked = unmarkedCount(session)

  return (
    <Panel className="flex flex-wrap items-center gap-x-14 gap-y-8 border-y border-rule py-8">
      <div className="flex flex-col gap-2.5">
        <span className="text-12 font-medium capitalize text-graphite">{noun} taken</span>
        <OccupancyMark taken={taken} capacity={session.capacity} size="lg" />
      </div>

      <Figure value={taken}>
        of {session.capacity} {noun}
        {free === 0 ? ', full' : ''}
      </Figure>

      {finished ? (
        <>
          {session.attended_count > 0 && (
            <>
              <Rule />
              <Figure value={session.attended_count} tone="text-good-ink">
                attended
              </Figure>
            </>
          )}
          {session.no_show_count > 0 && (
            <>
              <Rule />
              <Figure value={session.no_show_count} tone="text-bad-ink">
                absent
              </Figure>
            </>
          )}
          {unmarked > 0 && (
            <>
              <Rule />
              <Figure value={unmarked} tone="text-wait-ink">
                still to mark
              </Figure>
            </>
          )}
        </>
      ) : (
        <>
          {session.waitlisted_count > 0 && (
            <>
              <Rule />
              <Figure value={session.waitlisted_count} tone="text-wait-ink">
                waiting
              </Figure>
            </>
          )}
          {free > 0 && (
            <>
              <Rule />
              <span className="text-14 text-graphite">
                {free} {spotNoun(session.discipline, free !== 1)} still free
              </span>
            </>
          )}
        </>
      )}

      <span
        className="ml-auto h-10 w-[3px] rounded-full"
        style={{ background: disciplineColor(session.discipline) }}
        aria-hidden="true"
      />
    </Panel>
  )
}

/**
 * A figure at 36px with its label beside it.
 *
 * The only place in the app that uses the top of the type scale, and the only
 * place the width axis is applied to a number this large: at 85% width the
 * figures in a row line up as a set rather than as three separate headlines.
 */
function Figure({
  value,
  tone,
  children,
}: {
  value: number
  tone?: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-baseline gap-2">
      <span
        className={`condensed text-36 font-semibold tracking-[-0.02em] ${tone ?? ''}`}
        style={{ lineHeight: 1 }}
      >
        {value}
      </span>
      <span className="text-14 text-graphite">{children}</span>
    </div>
  )
}

function Rule() {
  return <span className="h-10 w-px bg-rule" aria-hidden="true" />
}
