import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'
import type { SortDirection } from '@/api/types'

/**
 * A column header that sorts.
 *
 * The arrow appears only on the column currently doing the sorting. Showing a
 * faint arrow on every sortable header — the common pattern — puts three
 * identical marks on the row and makes the one that means something harder to
 * find, which is the opposite of its job.
 *
 * `aria-sort` is what makes this work without sight of the arrow.
 */
export function SortableTh({
  children,
  active,
  direction,
  onClick,
  className,
}: {
  children: ReactNode
  active: boolean
  direction: SortDirection
  onClick: () => void
  className?: string
}) {
  return (
    <th
      scope="col"
      aria-sort={active ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'}
      className={cn('border-b border-rule px-4 pb-2.5 text-left', className)}
    >
      <button
        type="button"
        onClick={onClick}
        className={cn(
          'inline-flex items-center gap-1.5 text-12 font-medium',
          active ? 'text-ink' : 'text-graphite hover:text-ink',
        )}
      >
        {children}
        {active && (
          <svg
            width="9"
            height="9"
            viewBox="0 0 12 12"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.8"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
            className={direction === 'asc' ? 'rotate-180' : undefined}
          >
            <polyline points="2,4.5 6,8.5 10,4.5" />
          </svg>
        )}
      </button>
    </th>
  )
}
