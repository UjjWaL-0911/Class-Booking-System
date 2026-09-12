import { useCallback, useState } from 'react'
import type { Rule } from '@/lib/validation'

/**
 * When to show somebody they have got it wrong.
 *
 * Not while they are typing. A field that turns red on the first keystroke of an
 * email address is telling somebody they are wrong for the entire time they are
 * busy being right, and it is the commonest way form validation becomes an
 * irritant rather than a help.
 *
 * So an error appears once the field has been **left** — the person has finished
 * with it and can be told — or once **submit has been pressed**, which reveals
 * everything at once. After that the field re-checks on every keystroke, so the
 * message disappears the moment it is fixed rather than waiting for another blur.
 *
 * Submitting with anything invalid does not send the request. The button stays
 * enabled rather than greying out, deliberately: a disabled button that will not
 * say why is a dead end, and pressing it is how somebody asks the interface what
 * is wrong.
 */
export function useForm<K extends string>(errors: Partial<Record<K, Rule>>) {
  const [touched, setTouched] = useState<ReadonlySet<K>>(() => new Set())
  const [attempted, setAttempted] = useState(false)

  const failing = (Object.keys(errors) as K[]).filter((field) => errors[field] != null)
  const isValid = failing.length === 0

  /** The message for a field, but only once it is fair to show it. */
  const error = useCallback(
    (field: K): string | null => {
      if (!attempted && !touched.has(field)) return null
      return errors[field] ?? null
    },
    [attempted, touched, errors],
  )

  /** Call from a field's `onBlur`. */
  const touch = useCallback((field: K) => {
    setTouched((current) => {
      if (current.has(field)) return current
      const next = new Set(current)
      next.add(field)
      return next
    })
  }, [])

  /**
   * Run `action` only if every rule passes; otherwise reveal all the messages.
   *
   * Returns whether it went ahead, so a caller can decide what else to do —
   * though in practice nothing needs to, because the messages are already on the
   * fields they belong to.
   */
  const submit = useCallback(
    (action: () => void): boolean => {
      setAttempted(true)
      if (!isValid) return false
      action()
      return true
    },
    [isValid],
  )

  /** For a dialog that closes and will be opened again on a different record. */
  const reset = useCallback(() => {
    setTouched(new Set())
    setAttempted(false)
  }, [])

  return {
    error,
    touch,
    submit,
    reset,
    isValid,
    /** True once submit was pressed and refused — the cue for a summary line. */
    blocked: attempted && !isValid,
  }
}
