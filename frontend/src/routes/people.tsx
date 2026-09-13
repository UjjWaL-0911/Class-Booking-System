import { useState } from 'react'
import { PersonDialog } from '@/components/domain/person-dialog'
import { RateDialog } from '@/components/domain/rate-dialog'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/panel'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useCurrentUser } from '@/hooks/use-auth'
import { useTeachers } from '@/hooks/use-users'
import { Page, PageHeader } from '@/layout/app-shell'
import { cn } from '@/lib/cn'
import { formatMoney } from '@/lib/money'
import type { Teacher } from '@/api/types'

/**
 * The staff room.
 *
 * Not one of the ten goals, and the only screen here that isn't. It exists
 * because the goals assume it: goals 3, 5 and 7 all take an instructor *by id*,
 * and until this screen the only thing that could bring an instructor into
 * existence was the seed script. A studio that hired somebody in March had no way
 * to say so.
 *
 * Deliberately thin. It lists the people who can sign in, lets staff add one, and
 * lets staff set what each is paid to lead a session — and that is all. No name
 * changes, no deactivating, no password resets: each is a real feature with rules
 * of its own, and a row of buttons that only half-work would be worse than a list
 * that is honest about what it does.
 *
 * The rate is here rather than on the reports screen because this is the screen
 * about *people*, and because it is the answer to the only dead end payroll had:
 * "no rate set" was a thing the report could tell you and nothing could fix.
 *
 * Staff only. The nav link is hidden from an instructor and the server refuses
 * both endpoints for them, which is the half that actually enforces it.
 */
export function PeoplePage() {
  const me = useCurrentUser()
  const people = useTeachers()
  const [adding, setAdding] = useState(false)
  const [editingRate, setEditingRate] = useState<Teacher | null>(null)

  const staff = people.data?.filter((person) => person.role === 'staff') ?? []
  const instructors = people.data?.filter((person) => person.role === 'instructor') ?? []

  return (
    <Page>
      <PageHeader
        title="People"
        subtitle="Everyone who can sign in to the studio"
        actions={
          <Button variant="primary" onClick={() => setAdding(true)}>
            Add a person
          </Button>
        }
      />

      {people.isPending && <Skeleton rows={5} />}
      {people.error && <ErrorState error={people.error} onRetry={() => void people.refetch()} />}

      {people.data?.length === 0 && (
        <Panel>
          <EmptyState
            title="Nobody here yet"
            action={
              <Button size="sm" onClick={() => setAdding(true)}>
                Add a person
              </Button>
            }
          >
            Add the instructors who teach and the staff who run the desk.
          </EmptyState>
        </Panel>
      )}

      {/* Split by role rather than sorted into one list with a column. The two
          groups answer different questions — "who can I put in front of a class"
          and "who can change things" — and a reader scanning for one of them
          should not have to read the other. */}
      <Group title="Instructors" people={instructors} me={me.id} onEditRate={setEditingRate} />
      <Group title="Studio staff" people={staff} me={me.id} onEditRate={setEditingRate} />

      <PersonDialog open={adding} onOpenChange={setAdding} />
      <RateDialog person={editingRate} onClose={() => setEditingRate(null)} />
    </Page>
  )
}

function Group({
  title,
  people,
  me,
  onEditRate,
}: {
  title: string
  people: Teacher[]
  me: string
  onEditRate: (person: Teacher) => void
}) {
  if (people.length === 0) return null

  return (
    <Panel>
      <div className="flex items-baseline justify-between pb-1">
        <h2 className="text-12 font-medium text-graphite">{title}</h2>
        <span className="text-12 text-graphite">
          {people.length === 1 ? '1 person' : `${people.length} people`}
        </span>
      </div>
      {/* A list rather than a table, and no rules between the rows. Two fields
          per person do not need a grid drawn around them, and a divider under
          every name turns eight colleagues into a ledger. The columns still line
          up, which is the only thing the table was doing for us. */}
      <ul>
        {people.map((person) => (
          <li key={person.id} className={ROW}>
            <span className="truncate text-14 font-medium">
              {person.full_name}
              {person.id === me && (
                <span className="ml-2 text-11 font-normal text-graphite">You</span>
              )}
            </span>
            <span className="truncate text-14 text-graphite">{person.email}</span>
            {/* The figure is the button. A row of "Edit" buttons would put the
                same word next to every name and say nothing; the rate is the
                thing somebody came here to change, so it is the thing to click. */}
            <button
              type="button"
              onClick={() => onEditRate(person)}
              className="text-left text-14 tabular-nums hover:text-ink hover:underline sm:text-right"
            >
              {person.session_rate_minor === null ? (
                <span className="text-12 text-wait-ink">No rate set</span>
              ) : (
                formatMoney(person.session_rate_minor)
              )}
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

/** Name, email and rate, aligned in columns and stacked on a narrow screen. */
const ROW = cn(
  'grid grid-cols-1 gap-x-6 py-1.5 sm:items-baseline',
  'sm:grid-cols-[minmax(0,1fr)_minmax(0,34%)_112px]',
)
