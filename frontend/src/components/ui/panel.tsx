import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * A region of the page — not a card.
 *
 * This used to draw a border and a white fill on every section, on the argument
 * that borders should do the work shadows usually do. That argument was about
 * *elevation*, and it quietly answered a question nobody asked: a dashboard does
 * not need eight outlined boxes to say it has eight sections. Space says it, and
 * says it more calmly.
 *
 * So a region now has no border and no fill. What separates one from the next is
 * the gap between them and, where a section genuinely needs a lid, the single
 * hairline under its label. Elevation is still real, and still earned by
 * borders — but only on things that actually float: dialogs, the pickers inside
 * them, the popovers.
 *
 * `framed` is the escape hatch for those, and it is deliberately rare.
 */
export function Panel({
  children,
  className,
  padded = false,
  framed = false,
}: {
  children: ReactNode
  className?: string
  padded?: boolean
  /** Draws the old card. For something that sits above the page, not on it. */
  framed?: boolean
}) {
  return (
    <section
      className={cn(
        framed && 'rounded-md border border-rule bg-card',
        padded && (framed ? 'px-6 py-5' : 'py-1'),
        className,
      )}
    >
      {children}
    </section>
  )
}

/**
 * A region's label: a quiet word on the left, a fact on the right.
 *
 * The hairline beneath it is the only rule a section gets, and it is what makes
 * a borderless layout legible — the eye needs one horizontal to know where a
 * region begins. The right slot is for something the reader wants *before* they
 * look at the contents: how many rows, what the total is, which week. Never a
 * button; actions belong in the page header where there is one of them.
 */
export function PanelHeader({
  label,
  aside,
  className,
}: {
  label: ReactNode
  aside?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'mb-4 flex items-baseline justify-between gap-4 border-b border-rule pb-3',
        className,
      )}
    >
      <span className="tracked text-11 font-medium text-graphite">{label}</span>
      {aside && <span className="text-12 text-graphite">{aside}</span>}
    </div>
  )
}

/** The same thing, for a section that is not wrapped in a Panel. */
export function SectionLabel({ label, aside }: { label: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-4 border-b border-rule pb-3">
      <span className="tracked text-11 font-medium text-graphite">{label}</span>
      {aside}
    </div>
  )
}
