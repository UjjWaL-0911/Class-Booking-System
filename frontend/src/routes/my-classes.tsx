import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { Field, Select, TextInput } from '@/components/ui/field'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { PageHeader } from '@/layout/app-shell'
import { useOfferedClasses } from '@/hooks/use-me'
import { routes } from '@/lib/routes'
import type { OfferedClass } from '@/api/types'

/**
 * What the studio offers.
 *
 * A different question from the timetable, which is why it is a different screen
 * rather than a grouping of that one. The timetable answers "what can I do on
 * Thursday"; this answers "what does this place actually do" — the question
 * somebody asks once, when they are new, and then rarely again.
 *
 * So it reads like a menu rather than a list of rows: the description gets room,
 * because it is the only text on either screen that explains what a class *is*,
 * and each card leads into the timetable filtered to it. That link is the whole
 * point of the page — browsing ends in choosing a time.
 *
 * A class with nothing scheduled still appears, saying so. It is a real part of
 * what the studio does, and silence would imply it had been discontinued.
 */
export function MyClassesPage() {
  const classes = useOfferedClasses()
  const [query, setQuery] = useState('')
  const [discipline, setDiscipline] = useState('')

  // Depending on `classes.data` rather than on a defaulted copy: `?? []` builds a
  // new array on every render, so the memo would recompute every time and the
  // linter is right to say so.
  const disciplines = useMemo(
    () => [...new Set((classes.data ?? []).map((item) => item.discipline))].sort(),
    [classes.data],
  )
  const shown = useMemo(() => {
    const needle = query.trim().toLowerCase()
    return (classes.data ?? []).filter((item) => {
      if (discipline && item.discipline !== discipline) return false
      if (!needle) return true
      return `${item.title} ${item.discipline} ${item.description}`.toLowerCase().includes(needle)
    })
  }, [classes.data, query, discipline])

  return (
    <>
      <PageHeader
        title="Classes"
        subtitle="Everything the studio runs. Pick one to see when it is on."
      />

      <div className="flex flex-wrap items-end gap-5">
        <Field label="Search">
          {(id) => (
            <TextInput
              id={id}
              value={query}
              placeholder="Name or description"
              onChange={(event) => setQuery(event.target.value)}
              className="w-[240px]"
            />
          )}
        </Field>

        <Field label="Discipline">
          {(id) => (
            <Select
              id={id}
              value={discipline}
              onChange={(event) => setDiscipline(event.target.value)}
              className="w-[200px]"
            >
              <option value="">Every discipline</option>
              {disciplines.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </Select>
          )}
        </Field>
      </div>

      {classes.isPending && <Skeleton rows={5} />}
      {classes.error && (
        <ErrorState error={classes.error} onRetry={() => void classes.refetch()} />
      )}

      {classes.data && shown.length === 0 && (
        <EmptyState title="Nothing matches">
          Try a different search, or clear the discipline filter.
        </EmptyState>
      )}

      {shown.length > 0 && (
        <ul className="flex flex-col">
          {shown.map((item) => (
            <ClassRow key={item.id} offered={item} />
          ))}
        </ul>
      )}
    </>
  )
}

function ClassRow({ offered }: { offered: OfferedClass }) {
  return (
    <li className="border-b border-hairline py-6 last:border-b-0">
      <div className="flex flex-wrap items-baseline justify-between gap-x-8 gap-y-2">
        <h2 className="text-18 font-medium">{offered.title}</h2>
        <span className="text-12 text-graphite">
          {offered.discipline} · {offered.default_duration_min} minutes
        </span>
      </div>

      {offered.description && (
        <p className="mt-2 max-w-[68ch] text-14 leading-[1.65] text-graphite">
          {offered.description}
        </p>
      )}

      <p className="mt-3 text-12">
        {offered.upcoming_sessions === 0 ? (
          // Said plainly rather than hidden. A class with nothing on the
          // timetable has not been discontinued — archiving is what that means,
          // and an archived class is not on this page at all.
          <span className="text-graphite">Nothing scheduled in the next month</span>
        ) : (
          <Link
            to={routes.myTimetableForClass(offered.id)}
            className="text-graphite underline-offset-4 hover:text-ink hover:underline"
          >
            {offered.upcoming_sessions}{' '}
            {offered.upcoming_sessions === 1 ? 'session' : 'sessions'} coming up
          </Link>
        )}
      </p>
    </li>
  )
}
