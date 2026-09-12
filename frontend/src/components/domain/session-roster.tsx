import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { StatusChip } from './chips'
import { CancelBookingDialog, type CancelTarget } from './cancel-booking-dialog'
import { RosterRow, WaitingRow } from './roster-rows'
import { Panel, PanelHeader } from '@/components/ui/panel'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { Table, Th } from '@/components/ui/table'
import { useRoster } from '@/hooks/use-bookings'
import { spotNoun } from '@/lib/vocabulary'
import type { BookingListItem, Session, Uuid } from '@/api/types'
import { routes } from '@/lib/routes'

/**
 * Who is in the room, and who is waiting to be.
 *
 * Two tables rather than one with a status column, because they answer different
 * questions. The roster is a register: it gets numbered rows and, once the class
 * has finished, the two buttons that record attendance. The waiting list is a
 * queue: it gets positions, and the rule that governs it — an expired membership
 * is passed over — is stated on the row it applies to rather than in a tooltip.
 */
export function SessionRoster({ session }: { session: Session }) {
  const roster = useRoster(session.id)
  const [cancelling, setCancelling] = useState<CancelTarget | null>(null)
  const [promotedId, setPromotedId] = useState<Uuid | null>(null)

  const groups = useMemo(() => split(roster.data?.items ?? []), [roster.data])

  if (roster.isPending) {
    return (
      <Panel>
        <PanelHeader label="Roster" />
        <Skeleton rows={6} />
      </Panel>
    )
  }

  if (roster.error) {
    return (
      <Panel>
        <PanelHeader label="Roster" />
        <ErrorState error={roster.error} onRetry={() => void roster.refetch()} />
      </Panel>
    )
  }

  return (
    <>
      <Panel>
        <PanelHeader
          label="Roster"
          aside={summarise(groups.placed, session.discipline)}
        />
        {groups.placed.length === 0 ? (
          <EmptyState title={`Nobody has a ${spotNoun(session.discipline, false)} yet`}>
            Bookings taken at the desk appear here, in the order they were taken.
          </EmptyState>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th className="w-10 pr-2 text-right">&nbsp;</Th>
                <Th className="w-[30%]">Member</Th>
                <Th className="w-[22%]">Membership</Th>
                <Th className="w-[14%]">Booked</Th>
                <Th>Attendance</Th>
              </tr>
            </thead>
            <tbody>
              {groups.placed.map((booking, index) => (
                <RosterRow
                  key={booking.id}
                  booking={booking}
                  index={index}
                  session={session}
                  justPromoted={booking.id === promotedId}
                  onCancel={setCancelling}
                />
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      {groups.waiting.length > 0 && (
        <Panel>
          <PanelHeader
            label="Waiting"
            aside={`The top of the list takes the next ${spotNoun(session.discipline, false)} that opens`}
          />
          <Table>
            <tbody>
              {groups.waiting.map((booking, index) => (
                <WaitingRow
                  key={booking.id}
                  booking={booking}
                  position={index + 1}
                  session={session}
                  onCancel={setCancelling}
                />
              ))}
            </tbody>
          </Table>
        </Panel>
      )}

      {groups.cancelled.length > 0 && (
        <details className="border-t border-hairline pt-4">
          <summary className="cursor-pointer text-12 font-medium text-graphite">
            {groups.cancelled.length} cancelled{' '}
            {groups.cancelled.length === 1 ? 'booking' : 'bookings'}
          </summary>
          <ul className="mt-3 flex flex-col gap-1.5">
            {groups.cancelled.map((booking) => (
              <li key={booking.id} className="flex items-center justify-between gap-4">
                <Link
                  to={routes.bookingHistory(booking.id)}
                  className="text-14 underline-offset-2 hover:text-ink hover:underline"
                >
                  {booking.member_name}
                </Link>
                <StatusChip status={booking.status} />
              </li>
            ))}
          </ul>
        </details>
      )}

      <CancelBookingDialog
        target={cancelling}
        onClose={() => setCancelling(null)}
        onPromoted={setPromotedId}
      />
    </>
  )
}

/** Three groups: who has a place, who is queueing, and who has gone. */
function split(items: BookingListItem[]) {
  return {
    placed: items.filter((item) => ['booked', 'attended', 'no_show'].includes(item.status)),
    waiting: items.filter((item) => item.status === 'waitlisted'),
    cancelled: items.filter((item) => item.status === 'cancelled'),
  }
}

function summarise(placed: BookingListItem[], discipline: string): string {
  const attended = placed.filter((item) => item.status === 'attended').length
  const noShow = placed.filter((item) => item.status === 'no_show').length
  const unmarked = placed.filter((item) => item.status === 'booked').length

  if (attended === 0 && noShow === 0) {
    return `${placed.length} ${spotNoun(discipline, placed.length !== 1)} taken`
  }
  const parts = [`${attended} attended`]
  if (noShow > 0) parts.push(`${noShow} absent`)
  if (unmarked > 0) parts.push(`${unmarked} still to mark`)
  return parts.join(', ')
}
