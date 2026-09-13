import { Field } from '@/components/ui/field'

/**
 * Which days of the week a term covers.
 *
 * Toggles rather than a multi-select, because the whole set is seven items and a
 * closed control would hide six of them behind a click. `aria-pressed` is what
 * makes each one a toggle to a screen reader rather than a button that does
 * something when pressed.
 *
 * Selecting none means *every* day, which is the common case — somebody booking a
 * whole class for a term does not want to tick seven boxes first. The hint says so
 * rather than leaving an empty selection looking like an unfinished form.
 */
const DAYS = [
  { value: 0, label: 'Mon' },
  { value: 1, label: 'Tue' },
  { value: 2, label: 'Wed' },
  { value: 3, label: 'Thu' },
  { value: 4, label: 'Fri' },
  { value: 5, label: 'Sat' },
  { value: 6, label: 'Sun' },
]

export function WeekdayChooser({
  value,
  onChange,
}: {
  value: number[]
  onChange: (next: number[]) => void
}) {
  return (
    <Field
      label="Only these days"
      hint="Leave all unselected for every session of the class in the range"
    >
      {(id) => (
        <div id={id} className="flex flex-wrap gap-1.5 pt-1">
          {DAYS.map((day) => {
            const on = value.includes(day.value)
            return (
              <button
                key={day.value}
                type="button"
                aria-pressed={on}
                onClick={() =>
                  onChange(
                    on ? value.filter((d) => d !== day.value) : [...value, day.value],
                  )
                }
                className={
                  on
                    ? 'rounded-xs border border-ink bg-ink px-3 py-1.5 text-12 font-medium text-paper'
                    : 'rounded-xs border border-rule px-3 py-1.5 text-12 text-graphite hover:border-mute hover:text-ink'
                }
              >
                {day.label}
              </button>
            )
          })}
        </div>
      )}
    </Field>
  )
}
