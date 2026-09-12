import { useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { GenerateScheduleDialog } from '@/components/domain/generate-schedule-dialog'
import { ScheduleSessionDialog } from '@/components/domain/schedule-session-dialog'
import { SessionRow } from '@/components/domain/session-row'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/ui/panel'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useIsStaff } from '@/hooks/use-auth'
import { useClasses } from '@/hooks/use-classes'
import { useSessions } from '@/hooks/use-sessions'
import { useStudio } from '@/studio/studio-context'
import { Page, PageHeader } from '@/layout/app-shell'
import { addDays, formatDateLong, formatDayMonth, startOfWeek } from '@/lib/dates'
import { groupByDate } from '@/lib/sessions'

/**
 * The week (goals 3, 5 and 7).
 *
 * A week at a time, grouped by day, rather than a grid with an hour axis. A
 * calendar grid is the obvious shape and the wrong one for this studio: with two
 * or three classes a day it is mostly empty, and the empty space carries no
 * information. Grouped rows put every class on one readable line with its
 * occupancy, which is the thing being looked for.
 *
 * For an instructor this is goal 5's list — every session where they are the
 * primary or a co-instructor — produced by the server's visibility filter rather
 * than by a query this screen composes.
 *
 * With `?class=` it answers goal 3's last clause instead: "opening a class shows
 * its sessions". That is deliberately **not** week-bound. Somebody who has just
 * clicked a class is asking when it runs, not what it is doing between Monday and
 * Sunday, and a week's worth of one class is usually two rows and no answer.
 *
 * It also asks for archived classes in that mode. Goal 2 promises archiving hides
 * a class "without destroying its sessions or bookings", so opening an archived
 * class and being shown nothing would make the promise look false.
 */
export function TimetablePage() {
  const { today } = useStudio()
  const isStaff = useIsStaff()

  const [params, setParams] = useSearchParams()
  const classId = params.get('class')

  const [weekStart, setWeekStart] = useState(() => startOfWeek(today))
  const [scheduling, setScheduling] = useState(false)
  const [generating, setGenerating] = useState(false)

  const weekEnd = addDays(weekStart, 6)
  const sessions = useSessions(
    classId
      ? { class_id: classId, include_archived_classes: true, limit: 200 }
      : { date_from: weekStart, date_to: weekEnd, limit: 100 },
  )

  // The name comes from the classes list rather than from the first session,
  // because a class with no sessions yet is exactly the case this view has to
  // name — "nothing scheduled" is only useful when it says what for.
  const classes = useClasses(true)
  const focused = classId ? (classes.data?.find((c) => c.id === classId) ?? null) : null

  const byDay = useMemo(() => groupByDate(sessions.data?.items ?? []), [sessions.data])
  const isThisWeek = weekStart === startOfWeek(today)
  const total = sessions.data?.total ?? 0

  return (
    <Page>
      <PageHeader
        title={focused ? focused.title : 'Timetable'}
        subtitle={
          classId
            ? 'Every session of this class, past and future'
            : isStaff
              ? 'Every class in the studio this week'
              : 'Every class you are teaching or helping with this week'
        }
        actions={
          isStaff && (
            <>
              <Button onClick={() => setGenerating(true)}>Generate a schedule</Button>
              <Button variant="primary" onClick={() => setScheduling(true)}>
                Add a class
              </Button>
            </>
          )
        }
      />

      <div className="flex items-center justify-between gap-4 border-b border-rule pb-3">
        {classId ? (
          <>
            <div className="flex items-baseline gap-3">
              <h2 className="text-16 font-semibold tracking-[-0.01em]">
                {total === 1 ? '1 session' : `${total} sessions`}
              </h2>
              {focused?.archived_at !== null && focused !== null && (
                <span className="text-12 text-graphite">
                  This class is archived — its sessions are untouched
                </span>
              )}
            </div>
            <Button size="sm" onClick={() => setParams(new URLSearchParams(), { replace: true })}>
              The whole timetable
            </Button>
          </>
        ) : (
          <>
            <div className="flex items-baseline gap-3">
              <h2 className="text-16 font-semibold tracking-[-0.01em]">
                {formatDayMonth(weekStart)} to {formatDayMonth(weekEnd)}
              </h2>
              {isThisWeek && <span className="text-12 text-graphite">This week</span>}
            </div>
            <div className="flex gap-1.5">
              <Button size="sm" onClick={() => setWeekStart(addDays(weekStart, -7))}>
                Previous week
              </Button>
              {!isThisWeek && (
                <Button size="sm" onClick={() => setWeekStart(startOfWeek(today))}>
                  This week
                </Button>
              )}
              <Button size="sm" onClick={() => setWeekStart(addDays(weekStart, 7))}>
                Next week
              </Button>
            </div>
          </>
        )}
      </div>

      {sessions.isPending && <Skeleton rows={5} />}
      {sessions.error && <ErrorState error={sessions.error} onRetry={() => void sessions.refetch()} />}

      {sessions.data?.items.length === 0 && (
        <Panel>
          <EmptyState
            title={
              classId
                ? `${focused?.title ?? 'This class'} has never been scheduled`
                : 'Nothing scheduled this week'
            }
            action={
              isStaff && (
                <Button size="sm" onClick={() => setGenerating(true)}>
                  Generate a schedule
                </Button>
              )
            }
          >
            {classId
              ? 'Put it on the timetable once, or generate a repeating pattern for it.'
              : isStaff
                ? 'Add one class, or generate a repeating pattern for the whole month.'
                : 'You have no classes this week.'}
          </EmptyState>
        </Panel>
      )}

      {byDay.map(([date, daySessions]) => (
        <section key={date} className="flex flex-col gap-2.5">
          <div className="flex items-baseline justify-between border-b border-rule pb-2">
            <h3 className="text-12 font-medium text-graphite">
              {formatDateLong(date)}
              {date === today && <span className="ml-2 text-ink">Today</span>}
            </h3>
            <span className="text-12 text-graphite">
              {daySessions.length === 1 ? '1 class' : `${daySessions.length} classes`}
            </span>
          </div>
          {daySessions.map((session) => (
            <SessionRow key={session.id} session={session} />
          ))}
        </section>
      ))}

      {isStaff && (
        <>
          <ScheduleSessionDialog
            open={scheduling}
            onOpenChange={setScheduling}
            defaultDate={isThisWeek ? today : weekStart}
          />
          <GenerateScheduleDialog
            open={generating}
            onOpenChange={setGenerating}
            defaultDate={isThisWeek ? today : weekStart}
          />
        </>
      )}
    </Page>
  )
}
