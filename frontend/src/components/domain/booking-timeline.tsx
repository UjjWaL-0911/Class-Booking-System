import { useStudio } from '@/studio/studio-context'
import { formatInstantDay, formatInstantTime } from '@/lib/dates'
import { cn } from '@/lib/cn'
import type { BookingEvent } from '@/api/types'

/**
 * The immutable record (goal 9).
 *
 * Two decisions carry this component.
 *
 * **A hollow node means nobody did it.** `actor_name` is null exactly when
 * `is_system` is true — an automatic promotion, or the bulk cancellation behind a
 * removed class — and naming the staff member who happened to trigger it would be
 * a small lie in a log whose only value is being true. So those entries get a
 * ring instead of a filled mark and the word *automatically* where a name would
 * be.
 *
 * **The page says it cannot be changed.** Not as a disclaimer, but because the
 * guarantee is the feature: the database refuses updates and deletes on this
 * table, a correction is a new entry, and somebody reading a disputed booking
 * needs to know that what they are looking at is the whole of it.
 */
export function BookingTimeline({ events }: { events: BookingEvent[] }) {
  const { timeZone } = useStudio()

  return (
    <div className="flex flex-col">
      {events.map((event, index) => {
        const last = index === events.length - 1
        const { title, detail } = describe(event)

        return (
          <div key={event.id} className="flex gap-4">
            <div className="w-24 shrink-0 pt-px text-right">
              <p className="condensed text-14 font-medium">
                {formatInstantDay(event.occurred_at, timeZone)}
              </p>
              <p className="condensed text-12 text-graphite">
                {formatInstantTime(event.occurred_at, timeZone)}
              </p>
            </div>

            <div className="flex w-3 shrink-0 flex-col items-center">
              <span
                className={cn(
                  'mt-1.5 size-[9px] shrink-0 rounded-full',
                  event.is_system ? 'border-2 border-ink bg-paper' : 'bg-ink',
                )}
                aria-hidden="true"
              />
              {!last && <span className="mt-1.5 w-px flex-1 bg-rule" />}
            </div>

            <div className={cn('flex flex-col gap-1', last ? 'pb-2' : 'pb-6')}>
              <p className="text-14 font-medium">{title}</p>
              {detail && <p className="max-w-[68ch] text-14 text-graphite text-pretty">{detail}</p>}

              {event.note && (
                <p className="max-w-[68ch] border-l-2 border-rule pl-3 text-14 text-ink text-pretty">
                  {event.note}
                </p>
              )}

              <p className={cn('text-12 text-graphite', event.is_system && 'italic')}>
                {event.is_system ? 'automatically' : (event.actor_name ?? 'unknown')}
              </p>
            </div>
          </div>
        )
      })}
    </div>
  )
}

/**
 * What an entry means, in the studio's words.
 *
 * The raw transition — `waitlisted` to `booked` — is accurate and says nothing to
 * somebody trying to work out what happened to a member. "Given a spot" does.
 */
function describe(event: BookingEvent): { title: string; detail?: string } {
  if (event.event_type === 'note_added') {
    return { title: 'Note added' }
  }

  if (event.event_type === 'created') {
    return event.new_status === 'waitlisted'
      ? {
          title: 'Put on the waiting list',
          detail: 'The class was full, so this booking joined the queue for the next free spot.',
        }
      : { title: 'Booking taken' }
  }

  const from = event.old_status
  const to = event.new_status

  if (from === 'waitlisted' && to === 'booked') {
    return {
      title: 'Given a spot',
      detail: 'A spot opened and this booking was at the top of the waiting list.',
    }
  }
  if (to === 'cancelled') {
    return from === 'waitlisted'
      ? { title: 'Taken off the waiting list' }
      : { title: 'Cancelled', detail: 'The spot was freed for whoever was next in line.' }
  }
  if (to === 'attended') return { title: 'Marked as attended' }
  if (to === 'no_show') return { title: 'Marked as a no-show' }

  return { title: `${to ?? 'Status'} recorded` }
}
