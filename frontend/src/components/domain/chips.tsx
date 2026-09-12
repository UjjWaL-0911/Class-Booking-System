import { cn } from '@/lib/cn'
import { expiryPhrase } from '@/lib/dates'
import { ordinal } from '@/lib/vocabulary'
import type { BookingStatus } from '@/api/types'

/**
 * Every chip carries a hairline in its own colour, and that is not decoration.
 *
 * A pale wash on a beige page is almost exactly the page's luminance — the chip
 * was being told apart by hue alone, which is no help to anyone who cannot
 * separate those hues, and got worse as the ground darkened. The border gives it
 * a definite edge whatever the ground does, in the chip's own family so it costs
 * no new colour.
 */
const CHIP =
  'inline-flex items-center rounded-xs border px-[7px] py-[3px] text-11 font-medium'

const LABEL: Record<BookingStatus, string> = {
  booked: 'Booked',
  waitlisted: 'Waitlisted',
  attended: 'Attended',
  no_show: 'Absent',
  cancelled: 'Cancelled',
}

/**
 * Booking status **in a row of bookings**, where the one decision worth arguing
 * about is that booked carries no colour.
 *
 * Booked is what almost every row is. Colouring the normal state means colouring
 * nine rows in ten, and then the three states that actually need attention — a
 * queue, an absence, a cancellation — have nothing left to stand out against. So
 * booked is ink on nothing, cancelled is grey on nothing, and the washes are
 * spent where they buy something.
 *
 * Green goes to *attended*, not to booked, for the same reason. A booking is a
 * promise; attendance is a fact. Only one of those is worth a colour.
 */
const IN_A_LIST: Record<BookingStatus, string> = {
  booked: 'font-medium text-ink',
  waitlisted: cn(CHIP, 'border-wait-ink/25 bg-wait-wash text-wait-ink'),
  attended: cn(CHIP, 'border-good-ink/25 bg-good-wash text-good-ink'),
  no_show: cn(CHIP, 'border-bad-ink/25 bg-bad-wash text-bad-ink'),
  cancelled: 'text-graphite',
}

/**
 * The same statuses **as a set**, where that reasoning inverts.
 *
 * The argument above depends on one status appearing per row, surrounded by
 * rows that mostly say Booked. Stack all five in a single column — the reports
 * breakdown is the only place that does — and three drawn as chips beside two
 * drawn as bare words reads as two of them having failed to render, not as
 * emphasis. Nothing is being picked out of anything here; the column *is* the
 * five states, and a set has to look like a set.
 *
 * So booked and cancelled get the neutral chip: same shape, same border weight,
 * a wash one step off the page rather than a hue. They stay the quiet two, which
 * keeps the hierarchy, and they stop looking broken.
 */
const AS_A_SET: Record<BookingStatus, string> = {
  booked: cn(CHIP, 'border-mute bg-card text-ink'),
  waitlisted: IN_A_LIST.waitlisted,
  attended: IN_A_LIST.attended,
  no_show: IN_A_LIST.no_show,
  cancelled: cn(CHIP, 'border-mute bg-card text-graphite'),
}

interface StatusChipProps {
  status: BookingStatus
  /** 1-based place in the queue. Shown beside a waitlisted chip, never inside it. */
  position?: number | null
  /**
   * Every status drawn as a chip, including the two that are normally bare.
   * For the one screen that shows all five together — see `AS_A_SET`.
   */
  uniform?: boolean
  className?: string
}

export function StatusChip({ status, position, uniform = false, className }: StatusChipProps) {
  const label = LABEL[status]
  const variant = uniform ? AS_A_SET[status] : IN_A_LIST[status]

  if (status === 'waitlisted' && position) {
    return (
      <span className={cn('inline-flex items-center gap-1.5', className)}>
        <span className={variant}>{label}</span>
        <span className="text-11 text-graphite">{ordinal(position)}</span>
      </span>
    )
  }
  return <span className={cn(variant, className)}>{label}</span>
}

interface ExpiryChipProps {
  daysRemaining: number
  className?: string
}

/**
 * A membership expiry, shown only when it needs showing.
 *
 * Three states and one of them is silence: expired is the absence red, expiring
 * within a week is the waitlist amber, and a membership that is simply fine gets
 * nothing at all. That last case is the whole point — twenty-two members with
 * "valid" chips beside their names is twenty-two pieces of colour telling the
 * reader nothing, and the six who need a conversation disappear into them.
 */
export function ExpiryChip({ daysRemaining, className }: ExpiryChipProps) {
  const phrase = expiryPhrase(daysRemaining)
  if (phrase === null) return null

  const expired = daysRemaining < 0
  return (
    <span
      className={cn(
        CHIP,
        expired
          ? 'border-bad-ink/25 bg-bad-wash text-bad-ink'
          : 'border-wait-ink/25 bg-wait-wash text-wait-ink',
        className,
      )}
    >
      {phrase}
    </span>
  )
}
