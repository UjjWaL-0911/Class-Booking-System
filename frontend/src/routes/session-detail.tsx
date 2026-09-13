import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ApiError } from '@/api/errors'

import { CoInstructors } from '@/components/domain/co-instructors'
import { EditSessionDialog } from '@/components/domain/edit-session-dialog'
import { ExportRegisterButton } from '@/components/domain/export-register-button'
import { SessionOccupancy } from '@/components/domain/session-occupancy'
import { SessionRoster } from '@/components/domain/session-roster'
import { TakeBookingDialog } from '@/components/domain/take-booking-dialog'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Panel } from '@/components/ui/panel'
import { BootScreen, ErrorState } from '@/components/ui/states'
import { useToast } from '@/components/ui/toast-context'
import { useIsStaff } from '@/hooks/use-auth'
import { useDeleteSession, useSession } from '@/hooks/use-sessions'
import { Page, PageHeader } from '@/layout/app-shell'
import { formatDateLong, formatTimeRange } from '@/lib/dates'
import { hasFinished, hasStarted } from '@/lib/occupancy'
import { routes } from '@/lib/routes'

/**
 * One class, in full.
 *
 * The occupancy panel is the only place in the app where the marks are drawn at
 * 11px and the figures at 36px. This is the screen somebody is looking at while
 * standing in the doorway of the room, and it is the one moment where the count
 * deserves to be the largest thing present.
 */
export function SessionDetailPage() {
  const { sessionId = '' } = useParams()
  const navigate = useNavigate()
  const { notify } = useToast()
  const isStaff = useIsStaff()

  const session = useSession(sessionId)
  const deleteSession = useDeleteSession()

  const [booking, setBooking] = useState(false)
  const [editing, setEditing] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)

  if (session.isPending) return <BootScreen>Opening the class</BootScreen>
  if (session.error) {
    return (
      <Page>
        <ErrorState error={session.error} onRetry={() => void session.refetch()} />
        <Link to={routes.timetable} className="text-14 text-graphite hover:text-ink hover:underline">
          Back to the timetable
        </Link>
      </Page>
    )
  }

  const data = session.data
  const finished = hasFinished(data)
  // Not `finished`: the server stops accepting bookings the moment a class
  // starts, so an hour-long class is unbookable for the hour it is running.
  const started = hasStarted(data)

  return (
    <Page>
      <PageHeader
        back={
          <Link
            to={routes.timetable}
            className="inline-flex items-center gap-1.5 self-start text-12 text-graphite hover:text-ink hover:underline"
          >
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="7.5,2 3.5,6 7.5,10" />
            </svg>
            Timetable
          </Link>
        }
        title={data.class_title}
        subtitle={
          <span className="flex flex-wrap gap-x-4 gap-y-1">
            <span className="text-14 text-ink">
              {formatDateLong(data.session_date)}, {formatTimeRange(data.start_time, data.duration_min)}
            </span>
            <span className="text-14">{data.room_name}</span>
            {finished ? (
              <span className="text-14">This class has finished</span>
            ) : (
              started && <span className="text-14">This class is under way</span>
            )}
          </span>
        }
        actions={
          <>
            <ExportRegisterButton session={data} />
            {/* Editing stays available after the class has started — correcting
                the room or the instructor on a session that already ran is a
                normal thing to need, and the server refuses the parts that would
                not make sense. Taking a booking does not. */}
            {isStaff && (
              <Button onClick={() => setEditing(true)}>Edit this session</Button>
            )}
            {isStaff && !started && (
              <Button variant="primary" onClick={() => setBooking(true)}>
                Take a booking
              </Button>
            )}
          </>
        }
      />

      <SessionOccupancy session={data} />

      <div className="grid grid-cols-1 items-start gap-8 xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="flex min-w-0 flex-col gap-6">
          <SessionRoster session={data} />
        </div>

        <div className="flex flex-col gap-6">
          {isStaff ? (
            <CoInstructors session={data} />
          ) : (
            <Panel padded className="flex flex-col gap-2">
              <span className="text-12 font-medium text-graphite">Teaching this class</span>
              <span className="text-14 font-medium">{data.primary_instructor.full_name}</span>
              {data.co_instructors.map((person) => (
                <span key={person.id} className="text-14">
                  {person.full_name}
                </span>
              ))}
            </Panel>
          )}

          {isStaff && (
            <div className="flex flex-col items-start gap-2 px-1">
              <p className="max-w-[40ch] text-12 text-graphite text-pretty">
                Removing this class from the timetable cancels everyone still booked on it. Their
                booking history will say it was the studio's doing.
              </p>
              <Button variant="danger" size="sm" onClick={() => setConfirmDelete(true)}>
                Remove from the timetable
              </Button>
            </div>
          )}
        </div>
      </div>

      <TakeBookingDialog open={booking} onOpenChange={setBooking} session={data} />
      <EditSessionDialog session={data} open={editing} onOpenChange={setEditing} />

      <Dialog
        open={confirmDelete}
        onOpenChange={setConfirmDelete}
        title="Remove this class from the timetable"
        description={`${data.booked_count + data.waitlisted_count} ${data.booked_count + data.waitlisted_count === 1 ? 'person' : 'people'} will lose their place on ${data.class_title}.`}
        footer={
          <>
            <Button onClick={() => setConfirmDelete(false)}>Keep it</Button>
            <Button
              variant="danger"
              disabled={deleteSession.isPending}
              onClick={() =>
                deleteSession.mutate(data.id, {
                  onSuccess: () => {
                    notify('Removed from the timetable', {
                      detail: `${data.class_title} on ${formatDateLong(data.session_date)}.`,
                    })
                    void navigate('/timetable', { replace: true })
                  },
                })
              }
            >
              {deleteSession.isPending ? 'Removing' : 'Remove it'}
            </Button>
          </>
        }
      >
        <p className="text-14 text-graphite text-pretty">
          The class stays in the records — its bookings and their history are not deleted, so
          anyone can see what happened and when. It simply stops appearing on the timetable.
        </p>
        {deleteSession.error && (
          <p role="alert" className="mt-3 text-14 text-bad-ink">
            {deleteSession.error instanceof ApiError
              ? deleteSession.error.message
              : 'Could not remove that class.'}
          </p>
        )}
      </Dialog>
    </Page>
  )
}
