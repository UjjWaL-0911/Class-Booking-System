import { useMemo } from 'react'
import { Link } from 'react-router-dom'
import { ExportRegisterButton } from './export-register-button'
import { PanelHeader } from '@/components/ui/panel'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useSessions } from '@/hooks/use-sessions'
import { useStudio } from '@/studio/studio-context'
import { addDays, formatDateShort, formatTime } from '@/lib/dates'
import { hasFinished } from '@/lib/occupancy'
import { routes } from '@/lib/routes'
import { disciplineColor } from '@/lib/vocabulary'

/**
 * The registers, on the page somebody goes looking for them.
 *
 * The export itself belongs to a session — the brief asks for "a session's
 * attendance", and a register is a record of one class on one day rather than a
 * range. So the button lives on the session, and this is a second way in rather
 * than a second feature.
 *
 * It exists because that first way in was not findable. A manager wanting last
 * week's registers opens Reports, and being told the answer is on a page they
 * would have to remember to visit is a failure of the interface rather than of
 * the person.
 *
 * A fortnight, newest first. The sessions endpoint sorts ascending with no way
 * to reverse it, so the window is bounded by date and turned round here — asking
 * for "the last twelve" without a date bound would return the twelve *oldest*
 * sessions the studio ever ran.
 */
const DAYS_BACK = 14

export function RecentRegisters() {
  const { today } = useStudio()
  const sessions = useSessions({ date_from: addDays(today, -DAYS_BACK), date_to: today, limit: 80 })

  const finished = useMemo(
    () => [...(sessions.data?.items ?? [])].filter(hasFinished).reverse(),
    [sessions.data],
  )

  return (
    <section>
      <PanelHeader
        label="Registers"
        aside={`Classes that have run in the last ${DAYS_BACK} days`}
      />

      {sessions.isPending && <Skeleton rows={4} />}
      {sessions.error && (
        <ErrorState error={sessions.error} onRetry={() => void sessions.refetch()} />
      )}

      {sessions.data && finished.length === 0 && (
        <EmptyState title="No classes have finished in the last fortnight">
          A register can be exported once its class has run.
        </EmptyState>
      )}

      {finished.length > 0 && (
        <ul>
          {finished.map((session) => {
            const marked = session.attended_count + session.no_show_count
            return (
              <li
                key={session.id}
                className="flex flex-wrap items-center gap-x-6 gap-y-3 border-b border-hairline py-4 last:border-b-0"
              >
                <span
                  className="h-8 w-[3px] shrink-0 rounded-full"
                  style={{ background: disciplineColor(session.discipline) }}
                  aria-hidden="true"
                />

                <div className="w-[124px] shrink-0">
                  <p className="condensed text-14 font-medium">
                    {formatDateShort(session.session_date)}
                  </p>
                  <p className="text-11 text-graphite">{formatTime(session.start_time)}</p>
                </div>

                <Link
                  to={routes.session(session.id)}
                  className="min-w-0 flex-1 text-14 font-medium underline-offset-4 hover:text-ink hover:underline"
                >
                  {session.class_title}
                </Link>

                <p className="w-[190px] shrink-0 text-12 text-graphite">
                  {marked === 0 ? (
                    <span className="text-wait-ink">Nobody marked yet</span>
                  ) : (
                    <>
                      {session.attended_count} attended
                      {session.no_show_count > 0 && `, ${session.no_show_count} absent`}
                      {session.booked_count > 0 && (
                        <span className="text-wait-ink">
                          , {session.booked_count} unmarked
                        </span>
                      )}
                    </>
                  )}
                </p>

                <ExportRegisterButton session={session} size="sm" label="Export CSV" />
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}
