import { useTheme } from '@/hooks/use-theme'
import { cn } from '@/lib/cn'
import type { ThemePreference } from '@/lib/theme'

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

/**
 * Three states, not two.
 *
 * A plain light/dark switch cannot express "whatever my laptop is doing", which
 * is what most people want and what this defaults to. So the control offers the
 * choice it actually has: **Auto** follows the operating system and keeps
 * following it, while Light and Dark are decisions that stick.
 *
 * A segmented control rather than a switch because a switch has to guess which
 * way is "on", and with three states there is no such thing. Words rather than a
 * sun and a moon: the rail is text-only throughout, and "Auto" has no glyph
 * anybody would read correctly anyway.
 *
 * `radiogroup` rather than three buttons, so a screen reader announces it as one
 * choice of three and the arrow keys move between them.
 */
export function ThemeToggle() {
  const { preference, resolved, setPreference } = useTheme()

  return (
    <div
      role="radiogroup"
      aria-label="Colour scheme"
      className="flex overflow-hidden rounded-sm border border-rule"
    >
      {OPTIONS.map((option) => {
        const active = preference === option.value
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setPreference(option.value)}
            className={cn(
              'flex-1 border-r border-rule py-1 text-11 transition-colors duration-[120ms] last:border-r-0',
              active
                ? 'bg-card font-medium text-ink'
                : 'bg-transparent text-graphite hover:bg-hairline hover:text-ink',
            )}
          >
            {option.label}
          </button>
        )
      })}
      {/* What "Auto" currently resolves to. Without this the control is silent
          about the only one of its three states whose effect is not in its own
          label. */}
      <span className="sr-only">
        {preference === 'auto' ? `Following the system, currently ${resolved}` : ''}
      </span>
    </div>
  )
}
