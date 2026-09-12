import { Field, Select } from '@/components/ui/field'

/**
 * Choose a class, a room, or somebody to teach.
 *
 * The two scheduling dialogs each ask all three, in exactly the same shape: a
 * label, a placeholder that names the choice, a list of records with an `id`, and
 * a validation message. Six near-identical eighteen-line blocks is six places for
 * the wiring to drift — one of them losing its `onBlur` and quietly never showing
 * an error is the sort of thing nobody notices.
 *
 * Generic over the record rather than over a union of the three types, so adding
 * a fourth kind of thing to choose from costs nothing here.
 */
export function ResourceField<T extends { id: string }>({
  label,
  placeholder,
  options,
  getLabel,
  value,
  onChange,
  onBlur,
  error,
  hint,
}: {
  label: string
  /** The empty option. Says what choosing does: "Choose who is teaching". */
  placeholder: string
  options: T[]
  getLabel: (option: T) => string
  value: string
  onChange: (value: string) => void
  onBlur: () => void
  error: string | null
  hint?: string
}) {
  return (
    <Field label={label} hint={hint} error={error}>
      {(id, describedBy) => (
        <Select
          id={id}
          aria-describedby={describedBy}
          invalid={error !== null}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
        >
          <option value="">{placeholder}</option>
          {options.map((option) => (
            <option key={option.id} value={option.id}>
              {getLabel(option)}
            </option>
          ))}
        </Select>
      )}
    </Field>
  )
}
