import type { InputHTMLAttributes, ReactNode, SelectHTMLAttributes, TextareaHTMLAttributes } from 'react'
import { useId } from 'react'
import { cn } from '@/lib/cn'

/**
 * Labels are sentence case at 12px in graphite, and they sit above the control.
 *
 * Not tracked-out capitals, which is the commonest tell of a generated
 * interface, and not floating labels, which hide the field name exactly when
 * somebody is checking what they typed.
 */
const LABEL = 'text-12 font-medium text-graphite'

const CONTROL = cn(
  'w-full rounded-sm border border-rule bg-card px-2.5 text-14 text-ink',
  'placeholder:text-mute transition-colors duration-[120ms] hover:border-mute',
  'disabled:bg-paper disabled:text-graphite',
)

interface FieldProps {
  label: string
  /** Shown under the control in graphite — a rule the person needs before typing. */
  hint?: string
  error?: string | null
  children: (id: string, describedBy: string | undefined) => ReactNode
}

export function Field({ label, hint, error, children }: FieldProps) {
  const id = useId()
  const messageId = `${id}-message`
  const message = error ?? hint
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className={LABEL}>
        {label}
      </label>
      {children(id, message ? messageId : undefined)}
      {message && (
        <p id={messageId} className={cn('text-12', error ? 'text-bad-ink' : 'text-graphite')}>
          {message}
        </p>
      )}
    </div>
  )
}

type TextInputProps = InputHTMLAttributes<HTMLInputElement> & { invalid?: boolean }

export function TextInput({ className, invalid, ...rest }: TextInputProps) {
  return (
    <input
      className={cn(CONTROL, 'h-[34px]', invalid && 'border-bad-ink', className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  )
}

type SelectProps = SelectHTMLAttributes<HTMLSelectElement> & { invalid?: boolean }

/**
 * A native `<select>`, on purpose.
 *
 * The pickers in this app choose from a room list, a staff list and a class list
 * — never more than a few dozen items, all of them short strings. A custom
 * listbox would cost a keyboard implementation, a screen-reader implementation
 * and a scroll-locking implementation to arrive at what the platform already
 * does correctly on a phone.
 */
export function Select({ className, invalid, children, ...rest }: SelectProps) {
  return (
    <select
      className={cn(CONTROL, 'h-[34px] appearance-none pr-8', invalid && 'border-bad-ink', className)}
      style={{
        // A chevron drawn in the token colour, rather than the platform arrow,
        // which is the one piece of native chrome that looks wrong here.
        backgroundImage:
          "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='12' height='12' viewBox='0 0 12 12' fill='none' stroke='%236A6E7A' stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='2,4.5 6,8.5 10,4.5'/%3E%3C/svg%3E\")",
        backgroundRepeat: 'no-repeat',
        backgroundPosition: 'right 10px center',
      }}
      aria-invalid={invalid || undefined}
      {...rest}
    >
      {children}
    </select>
  )
}

type TextAreaProps = TextareaHTMLAttributes<HTMLTextAreaElement> & { invalid?: boolean }

export function TextArea({ className, invalid, rows = 3, ...rest }: TextAreaProps) {
  return (
    <textarea
      rows={rows}
      className={cn(CONTROL, 'resize-y py-2 leading-normal', invalid && 'border-bad-ink', className)}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  )
}
