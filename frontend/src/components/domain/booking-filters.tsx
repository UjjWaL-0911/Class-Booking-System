import { Field, Select, TextInput } from '@/components/ui/field'
import { SearchInput } from '@/components/ui/search-input'
import { useClasses } from '@/hooks/use-classes'
import type { BookingStatus } from '@/api/types'

const STATUSES: { value: BookingStatus; label: string }[] = [
  { value: 'booked', label: 'Booked' },
  { value: 'waitlisted', label: 'Waitlisted' },
  { value: 'attended', label: 'Attended' },
  { value: 'no_show', label: 'Absent' },
  { value: 'cancelled', label: 'Cancelled' },
]

/**
 * Search, then narrow.
 *
 * Archived classes stay in the class filter — goal 2 keeps their sessions and
 * bookings, so leaving them out would hide records that still exist and make the
 * totals look wrong to anyone who counted them. They are labelled, not removed.
 *
 * The match count sits with the filters rather than above the table, because it
 * is a fact *about* the filters: it changes when they change, and it belongs
 * where the cause is.
 *
 * The date range bounds the class dates, not when the bookings were taken — the
 * labels say "Class dates" for that reason. Both ends are inclusive, and either
 * alone is a valid open-ended range.
 */
export function BookingFilters({
  q,
  classId,
  status,
  from,
  to,
  matches,
  onChange,
}: {
  q: string
  classId: string
  status: string
  from: string
  to: string
  /** Undefined while the first page is still loading. */
  matches: number | undefined
  onChange: (changes: Record<string, string>) => void
}) {
  const classes = useClasses(true)

  // Shown rather than blocked, and neither input carries a native `min` or
  // `max`. Those looked like sensible belt-and-braces and were the opposite: with
  // `max={to}` on the start field, anybody who filled the end date first found
  // every later day greyed out in the picker, and had to clear one field to widen
  // their own range. Nothing is out of bounds here — a range weeks ahead is the
  // ordinary case, since bookings are taken well before the class runs — so the
  // only feedback is a sentence when the two ends are the wrong way round.
  const backwards = from !== '' && to !== '' && to < from

  return (
    <div className="flex flex-wrap items-center gap-2">
      <SearchInput
        value={q}
        onChange={(value) => onChange({ q: value })}
        placeholder="Search by member or class"
        className="w-[300px]"
      />

      <Select
        aria-label="Class"
        value={classId}
        onChange={(event) => onChange({ class: event.target.value })}
        className="w-[200px]"
      >
        <option value="">Every class</option>
        {(classes.data ?? []).map((item) => (
          <option key={item.id} value={item.id}>
            {item.title}
            {item.archived_at ? ' (archived)' : ''}
          </option>
        ))}
      </Select>

      <Select
        aria-label="Status"
        value={status}
        onChange={(event) => onChange({ status: event.target.value })}
        className="w-[160px]"
      >
        <option value="">Any status</option>
        {STATUSES.map((item) => (
          <option key={item.value} value={item.value}>
            {item.label}
          </option>
        ))}
      </Select>

      <div className="flex-1" />

      {matches !== undefined && (
        <span className="text-12 text-graphite">
          {matches === 1 ? '1 booking matches' : `${matches} bookings match`}
        </span>
      )}

      {/* The range sits on its own line. Two date inputs alongside three other
          controls wraps badly at anything under a wide window, and a filter that
          lands on a second row by accident looks like a mistake rather than a
          group. */}
      <div className="flex w-full flex-wrap items-end gap-3">
        <Field label="Class dates from" error={null}>
          {(id) => (
            <TextInput
              id={id}
              type="date"
              value={from}
              onChange={(event) => onChange({ from: event.target.value })}
              className="w-[168px]"
            />
          )}
        </Field>

        <Field
          label="until"
          error={backwards ? 'This is before the start date.' : null}
        >
          {(id, describedBy) => (
            <TextInput
              id={id}
              type="date"
              aria-describedby={describedBy}
              invalid={backwards}
              value={to}
              onChange={(event) => onChange({ to: event.target.value })}
              className="w-[168px]"
            />
          )}
        </Field>

        {(from || to) && (
          <button
            type="button"
            onClick={() => onChange({ from: '', to: '' })}
            className="mb-2 text-12 text-graphite underline-offset-2 hover:text-ink hover:underline"
          >
            Clear the dates
          </button>
        )}
      </div>
    </div>
  )
}
