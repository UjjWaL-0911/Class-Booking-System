import { useMemo, useState } from 'react'
import { Occupancy } from './occupancy-mark'
import { disciplineColor } from '@/lib/vocabulary'
import { Select, TextInput } from '@/components/ui/field'
import { Skeleton } from '@/components/ui/states'
import { useClasses } from '@/hooks/use-classes'
import { useSessions } from '@/hooks/use-sessions'
import { useStudio } from '@/studio/studio-context'
import { cn } from '@/lib/cn'
import { formatDateLong, formatTime } from '@/lib/dates'
import { hasStarted } from '@/lib/occupancy'
import { groupByDate } from '@/lib/sessions'
import type { Session } from '@/api/types'

/**
 * Choose a class to book somebody onto.
 *
 * This replaced a single `<select>`, and the reason is worth recording: a
 * dropdown can only show one line of text per option, so the one fact that
 * decides the choice — is there room — was invisible until you had already
 * chosen. You had to pick a class to find out whether you wanted it.
 *
 * So every row carries its own occupancy, in the same marks used everywhere else
 * in the app: filled for taken, ringed for free. Scanning the list answers "which
 * of these has space" without opening anything.
 *
 * Full classes are still listed, deliberately. Booking a full class is a real
 * action — it puts the member on the waiting list — so hiding them would remove a
 * feature rather than reduce clutter. The filter is there for somebody who only
 * wants the ones with room.
 */
export function SessionPicker({
  selected,
  onSelect,
  enabled,
}: {
  selected: Session | null
  onSelect: (session: Session | null) => void
  /** Only queries while the dialog is open. */
  enabled: boolean
}) {
  const { today } = useStudio()
  const classes = useClasses()

  const [classId, setClassId] = useState('')
  const [from, setFrom] = useState(today)
  const [withRoomOnly, setWithRoomOnly] = useState(false)

  const query = useSessions(
    { date_from: from || today, class_id: classId || undefined, limit: 100 },
    enabled && selected === null,
  )

  const matches = useMemo(() => {
    const items = query.data?.items ?? []
    return items.filter(
      // A class that has started cannot be booked — the server refuses it — so
      // offering one is offering a dead end.
      (item) => !hasStarted(item) && (!withRoomOnly || item.seats_remaining > 0),
    )
  }, [query.data, withRoomOnly])

  const days = useMemo(() => groupByDate(matches), [matches])

  if (selected) return <ChosenSession session={selected} onChange={() => onSelect(null)} />

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Select
          aria-label="Class"
          value={classId}
          onChange={(event) => setClassId(event.target.value)}
          className="w-[180px]"
        >
          <option value="">Every class</option>
          {(classes.data ?? []).map((item) => (
            <option key={item.id} value={item.id}>
              {item.title}
            </option>
          ))}
        </Select>

        <TextInput
          type="date"
          aria-label="From this date"
          value={from}
          min={today}
          onChange={(event) => setFrom(event.target.value)}
          className="w-[160px]"
        />

        <label className="flex cursor-pointer select-none items-center gap-2 text-12 text-graphite">
          <input
            type="checkbox"
            checked={withRoomOnly}
            onChange={(event) => setWithRoomOnly(event.target.checked)}
            className="size-3.5 accent-ink"
          />
          Only ones with room
        </label>

        <div className="flex-1" />

        {!query.isPending && (
          <span className="text-12 text-graphite">
            {matches.length === 1 ? '1 class' : `${matches.length} classes`}
          </span>
        )}
      </div>

      <div
        role="radiogroup"
        aria-label="Class to book"
        className="max-h-[280px] overflow-y-auto rounded-sm border border-rule"
      >
        {query.isPending && <Skeleton rows={4} />}

        {!query.isPending && matches.length === 0 && (
          <p className="px-4 py-6 text-14 text-graphite text-pretty">
            {withRoomOnly
              ? 'Every class in this range is full. Clear the filter to put somebody on a waiting list.'
              : 'Nothing is scheduled from this date onwards. Add a class under Timetable.'}
          </p>
        )}

        {days.map(([date, sessions]) => (
          <div key={date}>
            <p className="sticky top-0 border-b border-hairline bg-paper px-4 py-1.5 text-11 font-medium text-graphite">
              {formatDateLong(date)}
            </p>
            {sessions.map((session) => (
              <SessionOption key={session.id} session={session} onSelect={onSelect} />
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

/**
 * One class in the list.
 *
 * A radio rather than a button, because that is what this is: one choice from
 * many. The mark on the left is a ring that fills when chosen — the same language
 * as the occupancy marks beside it, so the row needs no new colour to say it is
 * selected.
 */
function SessionOption({
  session,
  onSelect,
}: {
  session: Session
  onSelect: (session: Session) => void
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={false}
      onClick={() => onSelect(session)}
      className={cn(
        'flex w-full items-center gap-3 border-b border-hairline py-2.5 pl-3 pr-4 text-left last:border-b-0',
        'transition-colors duration-[120ms] hover:bg-row',
      )}
    >
      <span className="size-3 shrink-0 rounded-full border border-mute" aria-hidden="true" />

      <span
        className="h-8 w-[3px] shrink-0 rounded-full"
        style={{ background: disciplineColor(session.discipline) }}
        aria-hidden="true"
      />

      <span className="condensed w-12 shrink-0 text-14 font-medium">
        {formatTime(session.start_time)}
      </span>

      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-14 font-medium">{session.class_title}</span>
        <span className="text-11 text-graphite">
          {session.room_name}, {session.primary_instructor.full_name}
        </span>
      </span>

      <Occupancy session={session} className="w-[180px] shrink-0" />
    </button>
  )
}

/** What the picker collapses to once a class is chosen. */
function ChosenSession({ session, onChange }: { session: Session; onChange: () => void }) {
  return (
    <div className="flex items-center gap-3 rounded-sm border border-rule bg-paper py-2.5 pl-3 pr-4">
      <span className="size-3 shrink-0 rounded-full bg-ink" aria-hidden="true" />
      <span
        className="h-8 w-[3px] shrink-0 rounded-full"
        style={{ background: disciplineColor(session.discipline) }}
        aria-hidden="true"
      />
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="text-14 font-medium">{session.class_title}</span>
        <span className="text-11 text-graphite">
          {formatDateLong(session.session_date)} at {formatTime(session.start_time)},{' '}
          {session.room_name}
        </span>
      </span>
      <Occupancy session={session} className="shrink-0" />
      <button
        type="button"
        onClick={onChange}
        className="shrink-0 text-12 text-graphite underline-offset-2 hover:text-ink hover:underline"
      >
        Change
      </button>
    </div>
  )
}
