import { useState } from 'react'
import { ClassCard } from '@/components/domain/class-card'
import { ClassDialog } from '@/components/domain/class-dialog'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/panel'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useClasses } from '@/hooks/use-classes'
import { useIsStaff } from '@/hooks/use-auth'
import { Page, PageHeader } from '@/layout/app-shell'
import type { StudioClass } from '@/api/types'

/**
 * What the studio teaches (goal 2).
 *
 * Archived classes are hidden behind a toggle rather than mixed in greyed out,
 * and the copy is careful about what archiving is: the class stops appearing
 * where a class can be chosen, and every session and booking it ever had stays
 * exactly where it was. That distinction is goal 2's actual requirement, and
 * "Delete" would be a lie about it — which is why the word does not appear.
 */
export function ClassesPage() {
  const isStaff = useIsStaff()
  const [showArchived, setShowArchived] = useState(false)
  const [editing, setEditing] = useState<StudioClass | null>(null)
  const [adding, setAdding] = useState(false)

  const classes = useClasses(showArchived)
  const active = (classes.data ?? []).filter((item) => item.archived_at === null)
  const archived = (classes.data ?? []).filter((item) => item.archived_at !== null)

  return (
    <Page>
      <PageHeader
        title="Classes"
        subtitle="The classes the studio runs, and the defaults each session starts from"
        actions={
          isStaff && (
            <Button variant="primary" onClick={() => setAdding(true)}>
              Add a class
            </Button>
          )
        }
      />

      <Panel>
        {classes.isPending && <Skeleton rows={5} />}
        {classes.error && <ErrorState error={classes.error} onRetry={() => void classes.refetch()} />}

        {classes.data && active.length === 0 && (
          <EmptyState
            title="No classes yet"
            action={
              isStaff && (
                <Button size="sm" onClick={() => setAdding(true)}>
                  Add a class
                </Button>
              )
            }
          >
            A class is a template — a title, a length and a capacity. Sessions on the timetable are
            made from it.
          </EmptyState>
        )}

        {active.length > 0 && (
          <ClassList classes={active} isStaff={isStaff} onEdit={setEditing} />
        )}
      </Panel>

      <div className="flex items-center gap-4">
        <button
          type="button"
          onClick={() => setShowArchived((current) => !current)}
          className="text-12 text-graphite underline-offset-2 hover:text-ink hover:underline"
        >
          {showArchived ? 'Hide archived classes' : 'Show archived classes'}
        </button>
        {showArchived && archived.length === 0 && classes.data && (
          <span className="text-12 text-graphite">Nothing has been archived.</span>
        )}
      </div>

      {showArchived && archived.length > 0 && (
        <Panel>
          <p className="pb-4 text-12 text-graphite text-pretty">
            These are off the list of classes a session can be made from. Their sessions and
            bookings are untouched, and restoring a class puts it straight back.
          </p>
          <ClassList classes={archived} isStaff={isStaff} onEdit={setEditing} />
        </Panel>
      )}

      {isStaff && (
        <>
          <ClassDialog open={adding} onOpenChange={setAdding} />
          <ClassDialog
            open={editing !== null}
            onOpenChange={(next) => !next && setEditing(null)}
            studioClass={editing}
          />
        </>
      )}
    </Page>
  )
}

/**
 * The classes, as a list rather than a table.
 *
 * A studio has a handful of these and each one carries a paragraph, so rows of
 * fixed-width cells were fighting the content. Reading down a list is also how
 * somebody uses this screen: they are looking for the class they want to change,
 * not comparing a column of numbers.
 */
function ClassList({
  classes,
  isStaff,
  onEdit,
}: {
  classes: StudioClass[]
  isStaff: boolean
  onEdit: (studioClass: StudioClass) => void
}) {
  return (
    <div className="flex flex-col">
      {classes.map((item) => (
        <ClassCard key={item.id} studioClass={item} isStaff={isStaff} onEdit={onEdit} />
      ))}
    </div>
  )
}
