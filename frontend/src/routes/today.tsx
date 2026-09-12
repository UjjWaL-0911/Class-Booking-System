import { useState } from 'react'
import { Link } from 'react-router-dom'
import { AlertsPanel } from '@/components/domain/alerts-panel'
import { AttendanceChart } from '@/components/domain/attendance-chart'
import { HeadlineCards } from '@/components/domain/headline-cards'
import { SessionRow } from '@/components/domain/session-row'
import { TakeBookingDialog } from '@/components/domain/take-booking-dialog'
import { Button } from '@/components/ui/button'
import { Panel, PanelHeader, SectionLabel } from '@/components/ui/panel'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useIsStaff } from '@/hooks/use-auth'
import { useSessions } from '@/hooks/use-sessions'
import { useStudio } from '@/studio/studio-context'
import { Page, PageHeader } from '@/layout/app-shell'
import { formatDateLong, formatTime } from '@/lib/dates'
import type { Session } from '@/api/types'
import { routes } from '@/lib/routes'

/**
 * The landing screen.
 *
 * Goal 8's four figures across the top, then today's classes, then the eight-week
 * chart and whatever needs chasing. The figures come first because they are the
 * question somebody asks on the way in — what is on, how busy, who didn't turn
 * up, who is waiting — and each card links to the rows behind its number, so the
 * answer is one click from the evidence.
 *
 * Instructors get the same screen. The server scopes every figure on it to the
 * sessions they teach, so their cards describe their own morning — no separate
 * route, no role branch except the two things they genuinely cannot do.
 */
export function TodayPage() {
  const { today, timeZone, dashboard } = useStudio()
  const isStaff = useIsStaff()
  const [booking, setBooking] = useState(false)

  const sessions = useSessions({ date_from: today, date_to: today, limit: 20 })

  return (
    <Page>
      <PageHeader
        title={formatDateLong(today)}
        subtitle={`Everything below is in studio time, ${timeZone}`}
        actions={
          isStaff && (
            <Button variant="primary" onClick={() => setBooking(true)}>
              Take a booking
            </Button>
          )
        }
      />

      <HeadlineCards
        headline={dashboard.headline}
        weeks={dashboard.attendance_by_week}
        scope={isStaff ? 'studio' : 'yours'}
        nextUp={nextUp(sessions.data?.items)}
      />

      <section className="flex flex-col gap-2.5">
        <SectionLabel
          label="On today"
          aside={
            <Link
              to={routes.timetable}
              className="text-12 text-graphite underline-offset-2 hover:text-ink hover:underline"
            >
              Whole week
            </Link>
          }
        />

        {sessions.isPending && <Skeleton rows={2} />}
        {sessions.error && (
          <ErrorState error={sessions.error} onRetry={() => void sessions.refetch()} />
        )}

        {sessions.data?.items.length === 0 && (
          <Panel>
            <EmptyState
              title="Nothing is scheduled today"
              action={
                isStaff && (
                  <Link to={routes.timetable}>
                    <Button size="sm">Open the timetable</Button>
                  </Link>
                )
              }
            >
              {isStaff
                ? 'Add a class to the timetable and it will appear here.'
                : 'You are not teaching today.'}
            </EmptyState>
          </Panel>
        )}

        {sessions.data?.items.map((session) => <SessionRow key={session.id} session={session} />)}
      </section>

      <div
        className={
          isStaff
            ? 'grid grid-cols-1 items-start gap-8 xl:grid-cols-[minmax(0,1fr)_400px]'
            : 'grid grid-cols-1 items-start gap-8'
        }
      >
        <Panel className="px-6 pb-5 pt-0">
          <PanelHeader
            label="Bookings taken, by week"
            aside={`${dashboard.attendance_by_week.reduce((sum, week) => sum + week.attended + week.no_show, 0)} settled in eight weeks`}
            className="px-0"
          />
          <AttendanceChart weeks={dashboard.attendance_by_week} />
        </Panel>

        {isStaff && <AlertsPanel />}
      </div>

      <TakeBookingDialog open={booking} onOpenChange={setBooking} />
    </Page>
  )
}

/**
 * What the classes card says underneath its figure.
 *
 * The next class that has not started yet — which is the thing somebody at the
 * desk actually wants from "2 classes today". Undefined while the list is still
 * loading, so the card falls back to its own wording rather than flashing a
 * sentence that is about to change.
 */
function nextUp(sessions: Session[] | undefined): string | undefined {
  if (sessions === undefined) return undefined
  if (sessions.length === 0) return undefined

  const now = Date.now()
  const upcoming = sessions.find((session) => new Date(session.starts_at).getTime() > now)
  if (upcoming === undefined) {
    return sessions.length === 1 ? 'It has finished' : 'All of them have finished'
  }
  return `Next at ${formatTime(upcoming.start_time)}, ${upcoming.class_title}`
}
