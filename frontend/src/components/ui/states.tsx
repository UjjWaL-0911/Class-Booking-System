import type { ReactNode } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from './button'
import { cn } from '@/lib/cn'

/**
 * An empty screen is an invitation, not an apology.
 *
 * So every empty state says what would be here and offers the one action that
 * puts something here — never "No data found", which tells the reader only that
 * the software looked.
 */
export function EmptyState({
  title,
  children,
  action,
}: {
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-start gap-2 py-10">
      <p className="text-14 font-medium">{title}</p>
      {children && <p className="max-w-[52ch] text-14 text-graphite">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}

/**
 * A failed request, in the server's own words where it has any.
 *
 * The domain composes its rejections to be read — goal 4 requires a refused
 * booking to say why — so the message travels from the rule that raised it
 * straight to the screen. Substituting something friendlier here would throw away
 * the only sentence that explains what happened.
 */
export function ErrorState({
  error,
  onRetry,
  className,
}: {
  error: unknown
  onRetry?: () => void
  className?: string
}) {
  const message =
    error instanceof ApiError
      ? error.message
      : 'Something went wrong. Try again in a moment.'
  const retryable = !(error instanceof ApiError) || error.isRetryable || error.status >= 500

  return (
    <div className={cn('flex flex-col items-start gap-3 py-8', className)}>
      <p className="max-w-[60ch] text-14 text-ink">{message}</p>
      {onRetry && retryable && (
        <Button onClick={onRetry} size="sm">
          Try again
        </Button>
      )}
    </div>
  )
}

/**
 * A loading placeholder.
 *
 * Bars the shape of the rows that are coming, not a spinner. A spinner says
 * "wait"; a skeleton says "this is a table of eight rows", which is the thing
 * worth saying while a network request is in the air. It does not pulse:
 * animation on a placeholder draws the eye to the one part of the screen with
 * nothing to read.
 */
export function Skeleton({ rows = 5 }: { rows?: number }) {
  return (
    <div className="flex flex-col gap-px py-2" aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }, (_, index) => (
        <div key={index} className="flex h-10 items-center">
          <div
            className="h-3 rounded-xs bg-hairline"
            // Varying widths so it reads as text rather than as a bar chart.
            style={{ width: `${[46, 62, 38, 54, 44, 58, 40, 50][index % 8]}%` }}
          />
        </div>
      ))}
    </div>
  )
}

/** The boot screen, before the session and the studio's clock are known. */
export function BootScreen({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-6">
      <p className="text-14 text-graphite">{children}</p>
    </div>
  )
}
