import { Button } from './button'
import type { Page } from '@/api/types'

/**
 * Paging, stated in words rather than as numbered page buttons.
 *
 * Goal 6 asks for "pagination showing the total number of matches", and the total
 * is the part people actually use — a front desk searching a surname wants to
 * know whether it found one Delgado or eleven, not which of four pages to click.
 * Previous and next cover the rest.
 */
export function Pagination<T>({
  page,
  noun,
  onOffsetChange,
}: {
  page: Page<T>
  /** Plural. "bookings", "members" — what is being counted. */
  noun: string
  onOffsetChange: (offset: number) => void
}) {
  const { total, limit, offset, items } = page
  const first = total === 0 ? 0 : offset + 1
  const last = offset + items.length

  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-12 text-graphite">
        {total === 0
          ? `No ${noun}`
          : total <= limit
            ? `${total} ${total === 1 ? noun.replace(/s$/, '') : noun}`
            : `Showing ${first} to ${last} of ${total}`}
      </span>
      {total > limit && (
        <div className="flex gap-1.5">
          <Button
            size="sm"
            onClick={() => onOffsetChange(Math.max(offset - limit, 0))}
            disabled={offset === 0}
          >
            Previous
          </Button>
          <Button size="sm" onClick={() => onOffsetChange(offset + limit)} disabled={last >= total}>
            Next
          </Button>
        </div>
      )}
    </div>
  )
}
