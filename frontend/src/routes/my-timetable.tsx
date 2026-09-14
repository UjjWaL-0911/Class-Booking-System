import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { SessionList } from '@/components/domain/bookable-session-row'
import { Field, Select, TextInput } from '@/components/ui/field'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { PageHeader } from '@/layout/app-shell'
import { useBookableSessions, useOfferedClasses } from '@/hooks/use-me'
import { formatDateLong } from '@/lib/dates'
import type { BookableSession } from '@/api/types'

type Sort = 'soonest' | 'places'

/**
 * What is on, and one button per class.
 *
 * **The filtering is done in the browser, deliberately.** The whole window is one
 * request — forward-only, capped at 200 sessions — so it is already here by the
 * time somebody types. Sending each keystroke to the server would add a round
 * trip to a decision the client can make instantly, and a debounce to hide it.
 * The staff bookings list filters server-side for the opposite reason: it pages
 * across the studio's entire history, where the set is unbounded and the client
 * has seen almost none of it.
 *
 * Grouped by day when sorted by time, because somebody choosing a class is
 * choosing a *day* first. Sorting by availability drops the grouping — at that
 * point the question is "where is there room", and day headings would scatter the
 * answer across a dozen sections.
 */
export function MyTimetablePage() {
  const [params, setParams] = useSearchParams()
  const schedule = useBookableSessions()
  const classes = useOfferedClasses()

  const [query, setQuery] = useState('')
  const [sort, setSort] = useState<Sort>('soonest')
  const classId = params.get('class') ?? ''

  const sessions = useMemo(
    () => arrange(schedule.data ?? [], { query, classId, sort }),
    [schedule.data, query, classId, sort],
  )

  const chosen = classes.data?.find((item) => item.id === classId)

  return (
    <>
      <PageHeader
        title="Timetable"
        subtitle={
          chosen
            ? `${chosen.title} over the next fortnight`
            : 'Everything on over the next fortnight. Booking is instant — a full class puts you on the waiting list.'
        }
      />

      <div className="flex flex-wrap items-end gap-5">
        <Field label="Search">
          {(id) => (
            <TextInput
              id={id}
              value={query}
              placeholder="Class, instructor or room"
              onChange={(event) => setQuery(event.target.value)}
              className="w-[240px]"
            />
          )}
        </Field>

        <Field label="Class">
          {(id) => (
            <Select
              id={id}
              value={classId}
              onChange={(event) => {
                const next = new URLSearchParams(params)
                if (event.target.value) next.set('class', event.target.value)
                else next.delete('class')
                setParams(next, { replace: true })
              }}
              className="w-[200px]"
            >
              <option value="">Every class</option>
              {(classes.data ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.title}
                </option>
              ))}
            </Select>
          )}
        </Field>

        <Field label="Order">
          {(id) => (
            <Select
              id={id}
              value={sort}
              onChange={(event) => setSort(event.target.value as Sort)}
              className="w-[180px]"
            >
              <option value="soonest">Soonest first</option>
              <option value="places">Most places left</option>
            </Select>
          )}
        </Field>
      </div>

      {schedule.isPending && <Skeleton rows={6} />}
      {schedule.error && (
        <ErrorState error={schedule.error} onRetry={() => void schedule.refetch()} />
      )}

      {schedule.data && sessions.length === 0 && (
        <EmptyState title="Nothing matches">
          {query || classId
            ? 'Try a different search, or clear the class filter.'
            : 'There are no classes on the timetable for the next two weeks.'}
        </EmptyState>
      )}

      {sort === 'soonest'
        ? groupByDay(sessions).map(([date, rows]) => (
            <section key={date} className="flex flex-col gap-3">
              <h2 className="text-12 font-medium text-graphite">{formatDateLong(date)}</h2>
              <SessionList rows={rows} />
            </section>
          ))
        : sessions.length > 0 && <SessionList rows={sessions} withDate />}
    </>
  )
}

/**
 * Search, filter and order, in that order.
 *
 * The search matches class, instructor and room together rather than offering
 * three boxes: a member looking for "Aryan" or "Studio A" is doing the same thing
 * as one looking for "Vinyasa", and making them choose which field first is work
 * the interface can do for them.
 */
function arrange(
  sessions: BookableSession[],
  { query, classId, sort }: { query: string; classId: string; sort: Sort },
): BookableSession[] {
  const needle = query.trim().toLowerCase()
  const matched = sessions.filter((session) => {
    if (classId && session.class_id !== classId) return false
    if (needle) {
      const haystack =
        `${session.class_title} ${session.instructor_name} ${session.room_name} ${session.discipline}`.toLowerCase()
      if (!haystack.includes(needle)) return false
    }
    return true
  })

  if (sort === 'places') {
    // A stable sort, so equal availability keeps chronological order underneath —
    // "most places left" should not shuffle Tuesday in among next Friday.
    return [...matched].sort((a, b) => b.spots_remaining - a.spots_remaining)
  }
  return matched
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
