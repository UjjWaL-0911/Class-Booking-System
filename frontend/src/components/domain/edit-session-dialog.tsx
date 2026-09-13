import { useEffect, useState } from 'react'
import { ResourceField } from './resource-field'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextInput } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { useRooms } from '@/hooks/use-classes'
import { useUpdateSession } from '@/hooks/use-sessions'
import { useTeachers } from '@/hooks/use-users'
import { spotsTaken } from '@/lib/occupancy'
import { chosen, dateChosen, LIMITS, wholeNumber } from '@/lib/validation'
import { formatDateShort, formatTime } from '@/lib/dates'
import type { Session } from '@/api/types'

/**
 * Edit a scheduled session (goal 3).
 *
 * A separate dialog from the one that schedules a class, not one component with
 * an `editing` flag: scheduling picks a class, editing cannot. A session belongs
 * to one class for its whole life, and moving it would relocate its bookings — so
 * the class is shown here as a fact rather than a field.
 *
 * Three fields do more than they look like they do. **The instructor** is how a
 * substitute is arranged — the exclusion constraint refuses one already teaching
 * in that window, so the form does not have to pretend to know. **Capacity up**
 * fills the new seats from the waitlist in the same transaction, and the toast
 * says how many moved. **Capacity down** below the people already booked is
 * refused with a sentence naming the count, so the occupancy is shown beside the
 * field to make that refusal predictable.
 *
 * `version` travels with the request: two people editing from two stale forms
 * means the second gets a 409 rather than quietly overwriting the first.
 */
export function EditSessionDialog({
  session,
  open,
  onOpenChange,
}: {
  session: Session
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { notify } = useToast()
  const rooms = useRooms()
  const teachers = useTeachers()
  const updateSession = useUpdateSession()

  const [date, setDate] = useState(session.session_date)
  const [time, setTime] = useState(session.start_time.slice(0, 5))
  const [instructorId, setInstructorId] = useState(session.primary_instructor.id)
  const [roomId, setRoomId] = useState(session.room_id)
  const [duration, setDuration] = useState(String(session.duration_min))
  const [capacity, setCapacity] = useState(String(session.capacity))

  // The selects carry an empty option, so instructor and room can be blanked even
  // though they arrive populated. Same rules as the scheduling form.
  const form = useForm({
    session_date: dateChosen(date, 'a date'),
    start_time: dateChosen(time, 'a start time'),
    primary_instructor_id: chosen(instructorId, 'who is teaching'),
    room_id: chosen(roomId, 'a room'),
    duration_min: wholeNumber(duration, LIMITS.duration),
    capacity: wholeNumber(capacity, LIMITS.capacity),
  })
  const { reset: resetForm } = form

  // Reset on open, not on every render: the session refetches underneath while
  // this is closed, and reading props into state would strand a half-typed edit.
  useEffect(() => {
    if (!open) return
    setDate(session.session_date)
    setTime(session.start_time.slice(0, 5))
    setInstructorId(session.primary_instructor.id)
    setRoomId(session.room_id)
    setDuration(String(session.duration_min))
    setCapacity(String(session.capacity))
    resetForm()
  }, [open, session, resetForm])

  const taken = spotsTaken(session)
  const raising = Number(capacity) > session.capacity
  function close() {
    onOpenChange(false)
    updateSession.reset()
  }

  function submit() {
    updateSession.mutate(
      {
        id: session.id,
        body: {
          version: session.version,
          session_date: date,
          start_time: `${time}:00`,
          primary_instructor_id: instructorId,
          room_id: roomId,
          duration_min: Number(duration),
          capacity: Number(capacity),
        },
      },
      {
        onSuccess: (saved) => {
          // The server promotes in the same transaction, so the response already
          // knows who moved up. Saying so is the point of raising it.
          const promoted = saved.booked_count - session.booked_count
          notify('Saved', {
            tone: promoted > 0 ? 'good' : 'neutral',
            detail:
              promoted > 0
                ? `${promoted} ${promoted === 1 ? 'member' : 'members'} moved off the waiting list.`
                : `${saved.class_title} on ${formatDateShort(saved.session_date)} at ${formatTime(saved.start_time)}.`,
          })
          close()
        },
      },
    )
  }

  const error = updateSession.error
  const message =
    error instanceof ApiError ? error.message : error ? 'Could not save that session.' : null
  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title="Edit this session"
      description={`${session.class_title}. Changing the instructor is how a substitute is arranged.`}
      width="lg"
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() => form.submit(submit)}
            disabled={updateSession.isPending}
          >
            {updateSession.isPending ? 'Saving' : 'Save changes'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <div className="grid grid-cols-2 gap-4">
          <Field label="Date" error={form.error('session_date')}>
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="date"
                aria-describedby={describedBy}
                invalid={form.error('session_date') !== null}
                value={date}
                onChange={(event) => setDate(event.target.value)}
                onBlur={() => form.touch('session_date')}
              />
            )}
          </Field>
          <Field label="Start time" error={form.error('start_time')}>
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="time"
                aria-describedby={describedBy}
                invalid={form.error('start_time') !== null}
                value={time}
                onChange={(event) => setTime(event.target.value)}
                onBlur={() => form.touch('start_time')}
              />
            )}
          </Field>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <ResourceField
            label="Instructor"
            placeholder="Choose who is teaching"
            options={teachers.data ?? []}
            getLabel={(person) => person.full_name}
            value={instructorId}
            onChange={setInstructorId}
            onBlur={() => form.touch('primary_instructor_id')}
            error={form.error('primary_instructor_id')}
          />
          <ResourceField
            label="Room"
            placeholder="Choose a room"
            options={rooms.data ?? []}
            getLabel={(room) => room.name}
            value={roomId}
            onChange={setRoomId}
            onBlur={() => form.touch('room_id')}
            error={form.error('room_id')}
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Length" hint="Minutes" error={form.error('duration_min')}>
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="number"
                inputMode="numeric"
                aria-describedby={describedBy}
                invalid={form.error('duration_min') !== null}
                value={duration}
                onChange={(event) => setDuration(event.target.value)}
                onBlur={() => form.touch('duration_min')}
              />
            )}
          </Field>
          <Field
            label="Capacity"
            hint={
              raising && session.waitlisted_count > 0
                ? `${session.waitlisted_count} waiting — the new places go to them`
                : `${taken} of ${session.capacity} taken`
            }
            error={form.error('capacity')}
          >
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="number"
                inputMode="numeric"
                aria-describedby={describedBy}
                invalid={form.error('capacity') !== null}
                value={capacity}
                onChange={(event) => setCapacity(event.target.value)}
                onBlur={() => form.touch('capacity')}
              />
            )}
          </Field>
        </div>

        {form.blocked && (
          <p role="alert" className="text-14 text-bad-ink">
            Nothing was saved. Check the fields marked above.
          </p>
        )}

        {message && (
          <p role="alert" className="text-14 text-bad-ink">
            {message}
          </p>
        )}
      </div>
    </Dialog>
  )
}
