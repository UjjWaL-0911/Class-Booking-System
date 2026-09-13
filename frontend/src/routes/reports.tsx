import { useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { AttendanceChart } from '@/components/domain/attendance-chart'
import { StatusChip } from '@/components/domain/chips'
import { HeadlineCards } from '@/components/domain/headline-cards'
import { OperationsPanels } from '@/components/domain/operations-panels'
import { RecentRegisters } from '@/components/domain/recent-registers'
import { Button } from '@/components/ui/button'
import { Panel, PanelHeader } from '@/components/ui/panel'
import { EmptyState } from '@/components/ui/states'
import { useIsStaff } from '@/hooks/use-auth'
import { useStudio } from '@/studio/studio-context'
import { keys } from '@/lib/query-keys'
import { Page, PageHeader } from '@/layout/app-shell'
import { addDays, formatDateLong } from '@/lib/dates'
import type { ClassCount, StatusCount } from '@/api/types'
import { routes } from '@/lib/routes'

/**
 * Goal 8 in full.
 *
 * Today shows the headline sentence and the chart, because that is as much as
 * somebody opening the app at 8am wants. This screen is where the breakdowns
 * live: every booking by status, and by class.
 *
 * Both breakdowns are bar-per-row rather than pie charts. A pie makes somebody
 * compare angles to answer "which class is busiest"; a sorted list of rows
 * answers it by being sorted, and the bars are there to show *by how much*.
 *
 * Every figure here is scoped to the viewer by the server. An instructor's
 * "bookings by class" describes the classes they teach, which is a more useful
 * report than the studio total would be and needs no explaining on the screen.
 *
 * The registers sit here too. The CSV export belongs to a session and its button
 * is on the session, but "export last week's registers" is a thing somebody does
 * from a reports page — and an export nobody can find is an export nobody uses.
 */
export function ReportsPage() {
  const { dashboard, today, timeZone } = useStudio()
  const isStaff = useIsStaff()
  const queryClient = useQueryClient()

  const settled = dashboard.attendance_by_week.reduce(
    (sum, week) => sum + week.attended + week.no_show,
    0,
  )

  return (
    <Page>
      <PageHeader
        title="Reports"
        subtitle={
          <>
            {isStaff ? 'The whole studio' : 'The classes you teach'}, as of{' '}
            {formatDateLong(today)} in {timeZone}
          </>
        }
        actions={
          <Button onClick={() => void queryClient.invalidateQueries({ queryKey: keys.dashboard })}>
            Refresh
          </Button>
        }
      />

      <HeadlineCards
        headline={dashboard.headline}
        weeks={dashboard.attendance_by_week}
        scope={isStaff ? 'studio' : 'yours'}
      />

      <Panel className="px-6 pb-5 pt-0">
        <PanelHeader
          label="Attendance, by week"
          aside={`${settled} bookings settled over eight weeks`}
          className="px-0"
        />
        {settled === 0 ? (
          <EmptyState title="No attendance recorded yet">
            Once a class has finished and the register is marked, the weeks appear here.
          </EmptyState>
        ) : (
          <AttendanceChart weeks={dashboard.attendance_by_week} />
        )}
      </Panel>

      {/* Both roles, scoped differently by the server: staff see every room and
          every instructor, an instructor sees their own pay and no utilisation.
          Reading what a colleague earns is the thing being prevented — not
          somebody checking what they are owed. */}
      <OperationsPanels from={addDays(today, -30)} to={today} />

      <RecentRegisters />

      <div className="grid grid-cols-1 items-start gap-8 xl:grid-cols-2">
        <Panel>
          <PanelHeader
            label="Every booking, by status"
            aside={`${total(dashboard.by_status)} in all`}
          />
          {dashboard.by_status.length === 0 ? (
            <EmptyState title="No bookings yet">
              Take a booking and it will be counted here.
            </EmptyState>
          ) : (
            <ul className="">
              {dashboard.by_status.map((row) => (
                <li
                  key={row.status}
                  className="flex h-11 items-center gap-4 border-b border-hairline last:border-b-0"
                >
                  <span className="w-[110px] shrink-0">
                    <StatusChip status={row.status} uniform />
                  </span>
                  <Bar value={row.count} peak={peak(dashboard.by_status)} />
                  <span className="w-12 shrink-0 text-right text-14 font-medium">{row.count}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>

        <Panel>
          <PanelHeader
            label="Bookings, by class"
            aside={dashboard.by_class.length > 0 ? 'Busiest first' : undefined}
          />
          {dashboard.by_class.length === 0 ? (
            <EmptyState title="Nothing booked yet">
              Classes appear here as soon as they have a booking on them.
            </EmptyState>
          ) : (
            <ul className="">
              {dashboard.by_class.map((row) => (
                <li
                  key={row.class_id}
                  className="flex h-11 items-center gap-4 border-b border-hairline last:border-b-0"
                >
                  <Link
                    to={routes.bookingsForClass(row.class_id)}
                    className="w-[160px] shrink-0 text-14 leading-[1.4] hover:text-ink hover:underline"
                  >
                    {row.class_title}
                  </Link>
                  <Bar value={row.count} peak={peakClass(dashboard.by_class)} />
                  <span className="w-12 shrink-0 text-right text-14 font-medium">{row.count}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </Page>
  )
}

/**
 * A row's share of the largest row.
 *
 * Scaled against the peak rather than the total, so the differences between the
 * smaller rows stay visible. Against a total, one dominant class flattens
 * everything else into identical slivers.
 */
function Bar({ value, peak: max }: { value: number; peak: number }) {
  return (
    <span className="flex-1" aria-hidden="true">
      <span
        className="block h-1.5 rounded-full bg-mute"
        style={{ width: `${Math.max((value / max) * 100, value > 0 ? 2 : 0)}%` }}
      />
    </span>
  )
}

function total(rows: StatusCount[]): number {
  return rows.reduce((sum, row) => sum + row.count, 0)
}

function peak(rows: StatusCount[]): number {
  return Math.max(...rows.map((row) => row.count), 1)
}

function peakClass(rows: ClassCount[]): number {
  return Math.max(...rows.map((row) => row.count), 1)
}
