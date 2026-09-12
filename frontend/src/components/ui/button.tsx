import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { cn } from '@/lib/cn'

type Variant = 'primary' | 'secondary' | 'quiet' | 'danger'
type Size = 'md' | 'sm'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  children: ReactNode
}

/**
 * There are four variants and that is the whole set.
 *
 * The primary action is **ink, not blue**. Blue is spent on the focus ring and
 * the current nav item, and a blue button would make every screen's chrome
 * compete with the one thing on it that carries colour for a reason — a
 * waitlisted chip, an expired membership. A near-black fill is as emphatic and
 * says nothing the data has not said.
 *
 * `danger` is the exception, and it is a *border*, not a fill. Cancelling a
 * booking and deleting a session are consequential but they are also routine; a
 * red-filled button used ten times a day stops meaning anything.
 */
const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-ink text-paper border border-ink hover:bg-ink-hover hover:border-ink-hover disabled:bg-mute disabled:border-mute',
  secondary:
    'bg-card text-ink border border-rule hover:border-mute hover:bg-paper disabled:text-mute disabled:hover:border-rule',
  quiet:
    'bg-transparent text-graphite border border-transparent hover:bg-hairline hover:text-ink disabled:text-mute disabled:hover:bg-transparent',
  danger:
    'bg-card text-bad-ink border border-bad-wash hover:border-bad-ink hover:bg-bad-wash disabled:text-mute disabled:border-rule',
}

const SIZES: Record<Size, string> = {
  // 34px and 28px. Both comfortably above the 24px that a dense table tempts you
  // towards and below the 40px that makes a toolbar look like a landing page.
  md: 'h-[34px] px-3.5 text-14',
  sm: 'h-7 px-2.5 text-12',
}

export function Button({
  variant = 'secondary',
  size = 'md',
  className,
  type = 'button',
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex shrink-0 items-center justify-center gap-1.5 rounded-sm font-medium',
        'transition-colors duration-[120ms] disabled:cursor-not-allowed',
        SIZES[size],
        VARIANTS[variant],
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  )
}
