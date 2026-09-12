import { createContext, useContext } from 'react'

/**
 * The toast context and its hook, kept apart from the provider component.
 *
 * A file that exports both a component and a hook breaks fast refresh — every
 * edit to the provider remounts the tree instead of patching it. Splitting is the
 * fix rather than silencing the warning, and it also makes the contract readable
 * on its own.
 */
export type ToastTone = 'neutral' | 'good' | 'wait' | 'bad'

export interface ToastOptions {
  tone?: ToastTone
  /** A second line, for the consequence: who got the spot that just opened. */
  detail?: string
}

export interface ToastApi {
  notify: (message: string, options?: ToastOptions) => void
}

export const ToastContext = createContext<ToastApi | null>(null)

export function useToast(): ToastApi {
  const value = useContext(ToastContext)
  if (value === null) throw new Error('useToast was called outside ToastProvider.')
  return value
}
