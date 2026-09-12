import { useCallback, useMemo, useRef, useState } from 'react'
import type { ReactNode } from 'react'
import { ToastContext, type ToastApi, type ToastTone } from './toast-context'
import { cn } from '@/lib/cn'

/**
 * Confirmation, in the same words as the button that caused it.
 *
 * "Book a member" produces "Booked". "Cancel the booking" produces "Cancelled".
 * The vocabulary of an interface is how somebody learns their way around it, and
 * a button and its result that disagree make the person wonder whether the thing
 * they pressed is the thing that happened.
 *
 * Tones map onto the same three washes the status chips use, so a promotion
 * message and a waitlisted chip are visibly about the same idea.
 */
interface Toast {
  id: number
  message: string
  tone: ToastTone
  detail?: string
}

const TONES: Record<ToastTone, string> = {
  neutral: 'border-rule bg-card text-ink',
  good: 'border-good-wash bg-good-wash text-good-ink',
  wait: 'border-wait-wash bg-wait-wash text-wait-ink',
  bad: 'border-bad-wash bg-bad-wash text-bad-ink',
}

const DISMISS_AFTER_MS = 5000

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(0)

  const notify = useCallback<ToastApi['notify']>((message, options) => {
    const id = nextId.current++
    setToasts((current) => [
      // Three at most. A stack that grows without limit covers the thing the
      // person is working on, which is the opposite of what a confirmation is for.
      ...current.slice(-2),
      { id, message, tone: options?.tone ?? 'neutral', detail: options?.detail },
    ])
    setTimeout(() => {
      setToasts((current) => current.filter((toast) => toast.id !== id))
    }, DISMISS_AFTER_MS)
  }, [])

  const api = useMemo(() => ({ notify }), [notify])

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div
        className="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-[min(360px,calc(100vw-40px))] flex-col gap-2"
        // Polite, not assertive: a confirmation should not interrupt somebody
        // mid-sentence in a screen reader.
        role="status"
        aria-live="polite"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            className={cn(
              'pointer-events-auto rounded-sm border px-3.5 py-2.5 shadow-overlay',
              TONES[toast.tone],
            )}
          >
            <p className="text-14 font-medium">{toast.message}</p>
            {toast.detail && <p className="mt-0.5 text-12 opacity-80">{toast.detail}</p>}
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
