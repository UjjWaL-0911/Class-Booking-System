import { useId, useMemo, useState } from 'react'
import { ExpiryChip } from './chips'
import { TextInput } from '@/components/ui/field'
import { useDebounced } from '@/hooks/use-debounced'
import { useMembers } from '@/hooks/use-members'
import { useStudio } from '@/studio/studio-context'
import { cn } from '@/lib/cn'
import { daysBetween } from '@/lib/dates'
import type { Member } from '@/api/types'

/**
 * Find a member by name or email.
 *
 * The results are rendered inline rather than in a floating popover. This picker
 * only ever appears inside a dialog, and a portal-mounted listbox inside a modal
 * is where focus management goes wrong — two layers each with an opinion about
 * where the keyboard should be.
 *
 * Each result carries its membership expiry, and that is the point rather than a
 * flourish: booking somebody whose membership has lapsed is refused by the server
 * (goal 4), so showing the expiry *before* the click turns a rejected booking into
 * a conversation about renewing.
 */
export function MemberPicker({
  selected,
  onSelect,
  autoFocus = false,
}: {
  selected: Member | null
  onSelect: (member: Member | null) => void
  autoFocus?: boolean
}) {
  const { today } = useStudio()
  const [term, setTerm] = useState('')
  const debounced = useDebounced(term)
  const listId = useId()
  const [activeIndex, setActiveIndex] = useState(0)

  // Two characters before asking. One letter matches most of the studio, which is
  // a list nobody reads and a query nobody wanted.
  const enabled = debounced.trim().length >= 2
  const results = useMembers({ q: debounced.trim(), limit: 8 }, enabled)

  const items = useMemo(() => results.data?.items ?? [], [results.data])

  if (selected) {
    const daysRemaining = daysBetween(today, selected.membership_expiry)
    return (
      <div className="flex items-center justify-between gap-3 rounded-sm border border-rule bg-paper px-3 py-2.5">
        <div className="flex min-w-0 flex-col">
          <span className="text-14 font-medium">{selected.full_name}</span>
          <span className="break-all text-11 text-graphite">{selected.email}</span>
        </div>
        <div className="flex shrink-0 items-center gap-3">
          <ExpiryChip daysRemaining={daysRemaining} />
          <button
            type="button"
            onClick={() => {
              onSelect(null)
              setTerm('')
            }}
            className="text-12 text-graphite underline-offset-2 hover:text-ink hover:underline"
          >
            Change
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2">
      <TextInput
        role="combobox"
        aria-expanded={items.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        autoFocus={autoFocus}
        placeholder="Search by name or email"
        value={term}
        onChange={(event) => {
          setTerm(event.target.value)
          setActiveIndex(0)
        }}
        onKeyDown={(event) => {
          if (items.length === 0) return
          if (event.key === 'ArrowDown') {
            event.preventDefault()
            setActiveIndex((index) => Math.min(index + 1, items.length - 1))
          } else if (event.key === 'ArrowUp') {
            event.preventDefault()
            setActiveIndex((index) => Math.max(index - 1, 0))
          } else if (event.key === 'Enter') {
            // The picker sits in a form; without this, Enter on a highlighted
            // result submits the booking to whoever happened to be first.
            event.preventDefault()
            const member = items[activeIndex]
            if (member) onSelect(member)
          }
        }}
      />

      {enabled && (
        <ul
          id={listId}
          role="listbox"
          className="max-h-[240px] overflow-y-auto rounded-sm border border-rule bg-card"
        >
          {results.isPending && <li className="px-3 py-2.5 text-12 text-graphite">Searching</li>}

          {!results.isPending && items.length === 0 && (
            <li className="px-3 py-2.5 text-12 text-graphite">
              Nobody matches “{debounced.trim()}”. Add them under Members first.
            </li>
          )}

          {items.map((member, index) => {
            const daysRemaining = daysBetween(today, member.membership_expiry)
            return (
              <li key={member.id} role="option" aria-selected={index === activeIndex}>
                <button
                  type="button"
                  onMouseEnter={() => setActiveIndex(index)}
                  onClick={() => onSelect(member)}
                  className={cn(
                    'flex w-full items-center justify-between gap-3 border-b border-hairline px-3 py-2 text-left last:border-b-0',
                    index === activeIndex && 'bg-paper',
                  )}
                >
                  <span className="flex min-w-0 flex-col">
                    <span className="text-14 font-medium">{member.full_name}</span>
                    <span className="break-all text-11 text-graphite">{member.email}</span>
                  </span>
                  <ExpiryChip daysRemaining={daysRemaining} className="shrink-0" />
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
