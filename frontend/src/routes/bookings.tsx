import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { BookingFilters } from '@/components/domain/booking-filters'
import { StatusChip } from '@/components/domain/chips'
import { TakeBookingDialog } from '@/components/domain/take-booking-dialog'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/panel'
import { Pagination } from '@/components/ui/pagination'
import { SortableTh } from '@/components/ui/sortable-th'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { PersonCell, Table, Td, Th, Tr } from '@/components/ui/table'
import { useBookings } from '@/hooks/use-bookings'
import { useIsStaff } from '@/hooks/use-auth'
import { useDebounced } from '@/hooks/use-debounced'
import { useStudio } from '@/studio/studio-context'
import { Page, PageHeader } from '@/layout/app-shell'
import { formatDateShort, formatInstant, formatTime } from '@/lib/dates'
import type { BookingSort, BookingStatus, SortDirection } from '@/api/types'
import { routes } from '@/lib/routes'


/**
 * Find a booking (goal 6).
 *
 * The filters live in the URL. That is what makes a search shareable — the alerts
 * panel links straight here with a member's email in `q`, and a colleague can be
 * sent "the waitlisted bookings on Vinyasa Flow" as a link rather than a set of
 * instructions.
 *
 * Sorting is on the column headers rather than in a dropdown, and only the three
 * columns the server can actually sort by are clickable. A header that looks
 * sortable and is not is worse than one that plainly is not.
 */
export function BookingsPage() {
  const { timeZone } = useStudio()
  const isStaff = useIsStaff()
  const [params, setParams] = useSearchParams()
  const [booking, setBooking] = useState(false)

  const q = params.get('q') ?? ''
  const classId = params.get('class') ?? ''
  const status = (params.get('status') ?? '') as BookingStatus | ''
  const sort = (params.get('sort') ?? 'booked_at') as BookingSort
  const direction = (params.get('dir') ?? 'desc') as SortDirection
  const from = params.get('from') ?? ''
  const to = params.get('to') ?? ''
  const offset = Number(params.get('offset') ?? 0)

  const debouncedQ = useDebounced(q)

  const bookings = useBookings({
    q: debouncedQ.trim() || undefined,
    class_id: classId || undefined,
    status: status || undefined,
    date_from: from || undefined,
    date_to: to || undefined,
    sort,
    direction,
    limit: 25,
    offset,
  })

  /** Every filter change resets paging — page 4 of a new search is not page 4. */
  function update(changes: Record<string, string>) {
    const next = new URLSearchParams(params)
    for (const [key, value] of Object.entries(changes)) {
      if (value === '') next.delete(key)
      else next.set(key, value)
    }
    if (!('offset' in changes)) next.delete('offset')
    setParams(next, { replace: true })
  }

  function toggleSort(column: BookingSort) {
    const nextDirection = sort === column && direction === 'desc' ? 'asc' : 'desc'
    update({ sort: column, dir: nextDirection })
  }

  return (
    <Page>
      <PageHeader
        title="Bookings"
        subtitle={
          isStaff
            ? 'Every booking taken at the desk'
            : 'Bookings on the classes you teach'
        }
        actions={
          isStaff && (
            <Button variant="primary" onClick={() => setBooking(true)}>
              Take a booking
            </Button>
          )
        }
      />

      <BookingFilters
        q={q}
        classId={classId}
        status={status}
        from={from}
        to={to}
        matches={bookings.data?.total}
        onChange={update}
      />

      <Panel>
        {bookings.isPending && <Skeleton rows={8} />}
        {bookings.error && (
          <ErrorState error={bookings.error} onRetry={() => void bookings.refetch()} />
        )}

        {bookings.data?.items.length === 0 && (
          <EmptyState
            title="No bookings match those filters"
            action={
              (q || classId || status || from || to) && (
                <Button size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
                  Clear the filters
                </Button>
              )
            }
          >
            {q
              ? `Nothing found for “${q.trim()}”. Searching matches a member's name or email, or a class title.`
              : 'Bookings appear here as soon as they are taken.'}
          </EmptyState>
        )}

        {bookings.data && bookings.data.items.length > 0 && (
          <Table>
            <thead>
              <tr>
                <Th className="w-[26%]">Member</Th>
                <Th className="w-[20%]">Class</Th>
                <SortableTh
                  className="w-[18%]"
                  active={sort === 'session'}
                  direction={direction}
                  onClick={() => toggleSort('session')}
                >
                  When
                </SortableTh>
                <SortableTh
                  className="w-[16%]"
                  active={sort === 'status'}
                  direction={direction}
                  onClick={() => toggleSort('status')}
                >
                  Status
                </SortableTh>
                <SortableTh
                  className="w-[14%]"
                  active={sort === 'booked_at'}
                  direction={direction}
                  onClick={() => toggleSort('booked_at')}
                >
                  Taken
                </SortableTh>
                <Th className="w-[6%] text-right">&nbsp;</Th>
              </tr>
            </thead>
            <tbody>
              {bookings.data.items.map((item) => (
                <Tr key={item.id}>
                  <Td>
                    <PersonCell name={item.member_name} email={item.member_email} />
                  </Td>
                  <Td>
                    <Link
                      to={routes.session(item.session_id)}
                      className="hover:text-ink hover:underline"
                    >
                      {item.class_title}
                    </Link>
                  </Td>
                  <Td>
                    {formatDateShort(item.session_date)}, {formatTime(item.session_start_time)}
                  </Td>
                  <Td>
                    <StatusChip status={item.status} />
                    {/* A waitlisted booking on a class that has already happened
                        is shown as it is rather than quietly rewritten — that
                        person never got in, and the record should say so. */}
                    {item.status === 'waitlisted' && item.session_has_passed && (
                      <span className="ml-2 text-11 text-graphite">never got a spot</span>
                    )}
                  </Td>
                  <Td className="text-graphite">{formatInstant(item.booked_at, timeZone)}</Td>
                  <Td className="text-right">
                    <Link
                      to={routes.bookingHistory(item.id)}
                      className="text-12 text-graphite hover:text-ink hover:underline"
                    >
                      History
                    </Link>
                  </Td>
                </Tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      {bookings.data && (
        <Pagination
          page={bookings.data}
          noun="bookings"
          onOffsetChange={(next) => update({ offset: String(next) })}
        />
      )}

      <TakeBookingDialog open={booking} onOpenChange={setBooking} />
    </Page>
  )
}
