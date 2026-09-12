import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { ExpiryChip } from '@/components/domain/chips'
import { MemberDialog } from '@/components/domain/member-dialog'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/panel'
import { Pagination } from '@/components/ui/pagination'
import { SearchInput } from '@/components/ui/search-input'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { PersonCell, Table, Td, Th, Tr } from '@/components/ui/table'
import { useIsStaff } from '@/hooks/use-auth'
import { useDebounced } from '@/hooks/use-debounced'
import { useMembers } from '@/hooks/use-members'
import { useStudio } from '@/studio/studio-context'
import { Page, PageHeader } from '@/layout/app-shell'
import { daysBetween, formatDayMonth } from '@/lib/dates'
import type { Member } from '@/api/types'
import { routes } from '@/lib/routes'

/**
 * The membership binder (goal 1), and where goal 10's alerts lead.
 *
 * Sorted by name rather than by expiry, because this screen is used to look
 * somebody up. The ones that need attention already have their own feed on Today,
 * and re-sorting the whole binder around six people would make the other sixteen
 * harder to find.
 *
 * The search box is the first thing focused. "Delgado" is how this screen is
 * used, ninety-nine times out of a hundred.
 *
 * It is not the same binder for both roles. Staff get all of it; an instructor
 * gets the people who have booked into a class they teach, because the server
 * scopes the endpoint that way — a membership expiry is personal data, and an
 * instructor covering one evening class has no business paging through the whole
 * studio. The heading and the empty state say which binder is on screen rather
 * than leaving an instructor to wonder where everybody went.
 */
export function MembersPage() {
  const { today } = useStudio()
  const isStaff = useIsStaff()
  const [params, setParams] = useSearchParams()
  const [editing, setEditing] = useState<Member | null>(null)
  const [adding, setAdding] = useState(false)

  const q = params.get('q') ?? ''
  const offset = Number(params.get('offset') ?? 0)
  const debouncedQ = useDebounced(q)

  const members = useMembers({ q: debouncedQ.trim() || undefined, limit: 25, offset })

  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === '') next.delete(key)
      else next.set(key, value)
    }
    if (!('offset' in changes)) next.delete('offset')
    setParams(next, { replace: true })
  }

  return (
    <Page>
      <PageHeader
        title="Members"
        subtitle={
          isStaff
            ? 'Everyone the studio can book into a class'
            : 'The people who have booked into a class you teach'
        }
        actions={
          isStaff && (
            <Button variant="primary" onClick={() => setAdding(true)}>
              Add a member
            </Button>
          )
        }
      />

      <div className="flex flex-wrap items-center gap-4">
        <SearchInput
          value={q}
          onChange={(value) => update({ q: value })}
          placeholder="Search by name or email"
          autoFocus
          className="w-[320px]"
        />
        <div className="flex-1" />
        {members.data && (
          <span className="text-12 text-graphite">
            {members.data.total === 1 ? '1 member' : `${members.data.total} members`}
          </span>
        )}
      </div>

      <Panel>
        {members.isPending && <Skeleton rows={8} />}
        {members.error && <ErrorState error={members.error} onRetry={() => void members.refetch()} />}

        {members.data?.items.length === 0 && (
          <EmptyState
            title={q ? `Nobody matches “${q.trim()}”` : 'No members yet'}
            action={
              isStaff && (
                <Button size="sm" onClick={() => setAdding(true)}>
                  Add a member
                </Button>
              )
            }
          >
            {q
              ? 'Searching matches a name or an email address.'
              : isStaff
                ? 'Add the people who come to classes, and the desk can book them in.'
                : 'People appear here once they have booked into one of your classes.'}
          </EmptyState>
        )}

        {members.data && members.data.items.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th className="w-[30%]">Member</Th>
                <Th className="w-[22%]">Membership</Th>
                <Th className="w-[30%]">Notes</Th>
                <Th className="w-[18%] text-right">&nbsp;</Th>
              </tr>
            </thead>
            <tbody>
              {members.data.items.map((member) => {
                const daysRemaining = daysBetween(today, member.membership_expiry)
                return (
                  <Tr key={member.id}>
                    <Td>
                      <PersonCell name={member.full_name} email={member.email} />
                    </Td>
                    <Td>
                      <div className="flex items-center gap-2.5">
                        <span className={daysRemaining < 0 ? 'text-graphite' : undefined}>
                          {formatDayMonth(member.membership_expiry)}
                        </span>
                        <ExpiryChip daysRemaining={daysRemaining} />
                      </div>
                    </Td>
                    <Td className="py-3 text-graphite">
                      {/* Wrapped, not clipped. The form accepts two thousand
                          characters here; showing the first six words and an
                          ellipsis meant the column was decoration. A long note
                          makes a tall row, which is the honest outcome. */}
                      {member.notes ? (
                        <span className="block max-w-[46ch] whitespace-pre-line leading-[1.6]">
                          {member.notes}
                        </span>
                      ) : (
                        <span className="text-mute">—</span>
                      )}
                    </Td>
                    <Td className="text-right">
                      <div className="flex items-center justify-end gap-4">
                        <Link
                          to={routes.bookingsFor(member.email)}
                          className="text-12 text-graphite hover:text-ink hover:underline"
                        >
                          Bookings
                        </Link>
                        {isStaff && (
                          <button
                            type="button"
                            onClick={() => setEditing(member)}
                            className="text-12 text-graphite hover:text-ink hover:underline"
                          >
                            Edit
                          </button>
                        )}
                      </div>
                    </Td>
                  </Tr>
                )
              })}
            </tbody>
          </Table>
        )}
      </Panel>

      {members.data && (
        <Pagination
          page={members.data}
          noun="members"
          onOffsetChange={(next) => update({ offset: String(next) })}
        />
      )}

      {isStaff && (
        <>
          <MemberDialog open={adding} onOpenChange={setAdding} />
          <MemberDialog
            open={editing !== null}
            onOpenChange={(next) => !next && setEditing(null)}
            member={editing}
          />
        </>
      )}
    </Page>
  )
}
