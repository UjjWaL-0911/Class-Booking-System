import type { ReactNode, ThHTMLAttributes, TdHTMLAttributes } from 'react'
import { cn } from '@/lib/cn'

/**
 * The table, at 40px rows.
 *
 * Dense enough that a full class fits on one screen, loose enough to click a row
 * action without aiming. Column headers are sentence case in graphite at 12px —
 * not tracked-out capitals, which shout the least useful text on the screen.
 *
 * Rows are separated by `hairline` rather than `rule`: twenty full-strength
 * dividers read as a grid, and the eye has to work past the structure to reach
 * the data.
 */
export function Table({ children, className }: { children: ReactNode; className?: string }) {
  // Its own horizontal scroller. The page body must never scroll sideways, but a
  // table with eight columns on a narrow screen legitimately does.
  return (
    <div className="-mx-1 overflow-x-auto px-1">
      <table className={cn('w-full min-w-[640px]', className)}>{children}</table>
    </div>
  )
}

export function Th({ className, children, ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      className={cn(
        'border-b border-rule px-4 pb-2.5 text-left text-12 font-medium text-graphite',
        className,
      )}
      {...rest}
    >
      {children}
    </th>
  )
}

export function Td({ className, children, ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td
      // `min-h` rather than a fixed height. A row is 40px when every cell holds
      // one line, and grows when one of them wraps — a fixed height would clip
      // the second line or let it run into the row below.
      className={cn('min-h-10 border-b border-hairline px-4 py-2.5 align-middle text-14', className)}
      {...rest}
    >
      {children}
    </td>
  )
}

/**
 * A row.
 *
 * `justPromoted` is the app's one orchestrated moment: when a cancellation hands
 * a spot to the next person in line, their row washes once from the waitlist
 * colour back to nothing. It runs for 320ms, it never repeats, and
 * `prefers-reduced-motion` removes it. Everything else in this interface holds
 * still.
 */
export function Tr({
  children,
  className,
  justPromoted = false,
  ...rest
}: {
  children: ReactNode
  className?: string
  justPromoted?: boolean
} & React.HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={cn(
        'last:[&>td]:border-b-0 hover:[&>td]:bg-row',
        justPromoted && 'animate-promoted',
        className,
      )}
      {...rest}
    >
      {children}
    </tr>
  )
}

/** A member's name with their email beneath it, the shape used in every list. */
export function PersonCell({ name, email }: { name: string; email?: string }) {
  return (
    <div className="flex flex-col">
      <span className="font-medium">{name}</span>
      {email && <span className="text-11 text-graphite">{email}</span>}
    </div>
  )
}
