import type { UserRole } from '@/api/types'

/**
 * One of the two things a person can be.
 *
 * A radio rather than an option in a dropdown. There are two choices, and the
 * difference between them is the most consequential thing on the form that uses
 * it — a closed select hides that difference behind a click and then shows only
 * whichever was picked. Each one carries a sentence saying what the role can
 * actually see and do, because "staff" and "instructor" are job titles and the
 * question being answered is about permissions.
 */
export function RoleChoice({
  value,
  current,
  onChange,
  label,
  detail,
}: {
  value: UserRole
  current: UserRole
  onChange: (role: UserRole) => void
  label: string
  detail: string
}) {
  return (
    <label className="flex cursor-pointer items-start gap-3">
      <input
        type="radio"
        name="role"
        className="mt-1 accent-ink"
        checked={current === value}
        onChange={() => onChange(value)}
      />
      <span>
        <span className="block text-14 font-medium">{label}</span>
        <span className="block text-12 leading-[1.5] text-graphite">{detail}</span>
      </span>
    </label>
  )
}
