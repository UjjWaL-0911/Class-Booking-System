import { Link } from 'react-router-dom'
import { cn } from '@/lib/cn'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast-context'
import { useArchiveClass, useRestoreClass } from '@/hooks/use-classes'
import { routes } from '@/lib/routes'
import { disciplineColor } from '@/lib/vocabulary'
import type { StudioClass } from '@/api/types'

/**
 * One class, at a size its description can actually live at.
 *
 * This was a table row with the description in a `line-clamp-1` cell, which meant
 * a field the form lets somebody write two thousand characters into was shown as
 * about six words followed by an ellipsis — and there was nowhere to read the
 * rest. A table is the right shape for bookings, where every row is the same
 * handful of short values; it is the wrong shape here, where the interesting
 * content is a paragraph and there are only ever a handful of classes.
 *
 * The title is a real button and the whole card is a click target, which are two
 * different mechanisms on purpose.
 *
 * The button is the control: it is in the tab order, a screen reader announces
 * it, and it works from the keyboard. It carries a permanent underline because
 * the first version had none — it was a word in medium weight that happened to
 * respond to clicks, and a control nobody can tell is a control may as well not
 * be one.
 *
 * The click handler on the card is a mouse convenience layered on top, not a
 * replacement. It is deliberately *not* the stretched-link trick, which covers
 * the card in an invisible anchor and takes text selection with it — this card's
 * whole purpose is a description somebody wants to read, and possibly copy. So it
 * is a plain handler that stands aside for anything that is already interactive
 * and for anything the reader has selected.
 *
 * Between them those two are the whole of editing: there was a third way in, an
 * explicit button in the action row, and once the title and the card both opened
 * the editor it was a button that said what the card already said.
 *
 * None of it renders for an instructor. That is goal 1 rather than a preference —
 * `PATCH /classes` refuses an instructor at the server, so showing the control
 * would only be offering a door that does not open.
 */
export function ClassCard({
  studioClass,
  isStaff,
  onEdit,
}: {
  studioClass: StudioClass
  isStaff: boolean
  onEdit: (studioClass: StudioClass) => void
}) {
  const { notify } = useToast()
  const archive = useArchiveClass()
  const restore = useRestoreClass()

  const isArchived = studioClass.archived_at !== null
  const busy = archive.isPending || restore.isPending

  return (
    <article
      className={cn(
        'group flex gap-6 border-b border-hairline py-7 last:border-b-0',
        isStaff && 'cursor-pointer',
      )}
      onClick={(event) => {
        if (!isStaff) return
        // Anything already interactive handles its own click.
        if ((event.target as HTMLElement).closest('button, a')) return
        // And a click that ended a text selection was a drag, not a press.
        if (window.getSelection()?.toString()) return
        onEdit(studioClass)
      }}
    >
      <span
        className="w-[3px] shrink-0 self-stretch rounded-full"
        style={{ background: disciplineColor(studioClass.discipline) }}
        aria-hidden="true"
      />

      <div className="flex min-w-0 flex-1 flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-2">
          <div className="min-w-0">
            {isStaff ? (
              <button
                type="button"
                onClick={() => onEdit(studioClass)}
                className={cn(
                  'text-16 font-medium underline decoration-1 underline-offset-4',
                  // Underlined at rest so it reads as a control before anybody
                  // has hovered anything, and it picks up the accent when the
                  // pointer is anywhere on the card — which is what says the
                  // whole card is the target.
                  'decoration-mute transition-colors duration-[120ms]',
                  'group-hover:text-ink group-hover:decoration-ink',
                )}
              >
                {studioClass.title}
              </button>
            ) : (
              <span className="text-16 font-medium">{studioClass.title}</span>
            )}
            <p className="tracked mt-1.5 text-11 text-graphite">{studioClass.discipline}</p>
          </div>

          <dl className="flex shrink-0 gap-8">
            <Fact label="Usual length">{studioClass.default_duration_min} min</Fact>
            <Fact label="Usual capacity">{studioClass.default_capacity}</Fact>
          </dl>
        </div>

        {/* The whole description, wrapped and capped for reading rather than
            clipped to the width of a column. */}
        {studioClass.description ? (
          <p className="max-w-[72ch] whitespace-pre-line text-14 leading-[1.7] text-graphite text-pretty">
            {studioClass.description}
          </p>
        ) : (
          <p className="text-14 text-mute">
            No description yet.
            {isStaff && ' Anyone booking this class would like to know what it is.'}
          </p>
        )}

        <div className="mt-1 flex flex-wrap items-center gap-2">
          {/* Goal 3's last clause, in as many words: "opening a class shows its
              sessions". It sat unbuilt for a while with the server ready for it —
              `GET /sessions` has taken a `class_id` filter all along — because
              nothing on this card ever asked. */}
          <Link to={routes.sessionsForClass(studioClass.id)}>
            <Button size="sm" variant="quiet">
              Its sessions
            </Button>
          </Link>
          <Link to={routes.bookingsForClass(studioClass.id)}>
            <Button size="sm" variant="quiet">
              Its bookings
            </Button>
          </Link>
          {isStaff && (
            <Button
              size="sm"
              variant="quiet"
              disabled={busy}
              onClick={() =>
                isArchived
                  ? restore.mutate(studioClass.id, {
                      onSuccess: () =>
                        notify('Restored', {
                          detail: `${studioClass.title} can be put on the timetable again.`,
                        }),
                    })
                  : archive.mutate(studioClass.id, {
                      onSuccess: () =>
                        notify('Archived', {
                          detail: `${studioClass.title} is off the list. Its sessions and bookings are untouched.`,
                        }),
                    })
              }
            >
              {isArchived ? 'Restore' : 'Archive'}
            </Button>
          )}
        </div>
      </div>
    </article>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="tracked text-11 text-graphite">{label}</dt>
      <dd className="text-14">{children}</dd>
    </div>
  )
}
