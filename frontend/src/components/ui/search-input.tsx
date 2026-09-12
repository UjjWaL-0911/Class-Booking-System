import { cn } from '@/lib/cn'

/**
 * The search field.
 *
 * A clear button appears once there is something to clear, rather than sitting
 * there greyed out. The focus treatment is on the wrapper rather than the input,
 * so the whole field lights up: this is what somebody types into first on two of
 * the screens, and the ring is how they know the keyboard is here.
 */
export function SearchInput({
  value,
  onChange,
  placeholder,
  className,
  autoFocus = false,
}: {
  value: string
  onChange: (value: string) => void
  placeholder: string
  className?: string
  autoFocus?: boolean
}) {
  return (
    <div
      className={cn(
        'flex h-[34px] items-center gap-2 rounded-sm border border-rule bg-card px-3',
        'transition-colors duration-[120ms] focus-within:border-ink',
        'focus-within:ring-[3px] focus-within:ring-ink/12',
        className,
      )}
    >
      <svg
        width="15"
        height="15"
        viewBox="0 0 20 20"
        fill="none"
        stroke="var(--color-graphite)"
        strokeWidth="1.6"
        strokeLinecap="round"
        className="shrink-0"
        aria-hidden="true"
      >
        <circle cx="9" cy="9" r="6" />
        <line x1="13.5" y1="13.5" x2="17" y2="17" />
      </svg>

      <input
        type="search"
        value={value}
        autoFocus={autoFocus}
        onChange={(event) => onChange(event.target.value)}
        placeholder={placeholder}
        aria-label={placeholder}
        // The ring lives on the wrapper, so the input itself must not draw a
        // second one inside it.
        className="min-w-0 flex-1 bg-transparent text-14 outline-none placeholder:text-mute [&::-webkit-search-cancel-button]:hidden"
      />

      {value !== '' && (
        <button
          type="button"
          onClick={() => onChange('')}
          aria-label="Clear the search"
          className="shrink-0 text-12 text-graphite hover:text-ink"
        >
          Clear
        </button>
      )}
    </div>
  )
}
