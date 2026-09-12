import { useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { ResourceField } from './resource-field'
import { Field, TextInput } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { useClasses, useRooms } from '@/hooks/use-classes'
import { useCreateSession, useTeachers } from '@/hooks/use-sessions'
import { formatDateShort, formatTime } from '@/lib/dates'
import { chosen, dateChosen, LIMITS, wholeNumber } from '@/lib/validation'
import type { LocalDate } from '@/api/types'

/**
 * Schedule one class (goal 3).
 *
 * Duration and capacity are left blank to inherit the class's defaults, and the
 * placeholder says which number that would be. The alternative — pre-filling the
 * inputs with the defaults — looks identical and is not: it turns every session
 * into an explicit override, so changing a class's capacity later stops affecting
 * anything already on the timetable.
 *
 * The two conflicts goal 3 cares about — a double-booked room, a double-booked
 * instructor — are enforced by exclusion constraints in the database, not checked
 * here. So this form does not try to predict them; it shows the server's sentence,
 * which names what it collided with.
 */
export function ScheduleSessionDialog({
  open,
  onOpenChange,
  defaultDate,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultDate: LocalDate
}) {
  const { notify } = useToast()
  const classes = useClasses()
  const rooms = useRooms()
  const teachers = useTeachers()
  const createSession = useCreateSession()

  const [classId, setClassId] = useState('')
  const [date, setDate] = useState(defaultDate)
  const [time, setTime] = useState('18:00')
  const [instructorId, setInstructorId] = useState('')
  const [roomId, setRoomId] = useState('')
  const [duration, setDuration] = useState('')
  const [capacity, setCapacity] = useState('')

  const chosenClass = classes.data?.find((item) => item.id === classId)

  const form = useForm({
    class_id: chosen(classId, 'a class'),
    session_date: dateChosen(date, 'a date'),
    start_time: dateChosen(time, 'a start time'),
    primary_instructor_id: chosen(instructorId, 'who is teaching'),
    room_id: chosen(roomId, 'a room'),
    // Blank is a valid answer for both: it means inherit the class default.
    duration_min: wholeNumber(duration, { ...LIMITS.duration, optional: true }),
    capacity: wholeNumber(capacity, { ...LIMITS.capacity, optional: true }),
  })

  function close() {
    onOpenChange(false)
    createSession.reset()
  }

  function submit() {
    createSession.mutate(
      {
        class_id: classId,
        session_date: date,
        // The API takes a wall-clock time; the browser's time input gives "18:00"
        // and the server pairs it with the studio's timezone. No conversion here,
        // deliberately — a client that converts is a client that can be wrong.
        start_time: `${time}:00`,
        primary_instructor_id: instructorId,
        room_id: roomId,
        duration_min: duration === '' ? null : Number(duration),
        capacity: capacity === '' ? null : Number(capacity),
      },
      {
        onSuccess: (session) => {
          notify('Scheduled', {
            tone: 'good',
            detail: `${session.class_title} on ${formatDateShort(session.session_date)} at ${formatTime(session.start_time)} in ${session.room_name}.`,
          })
          close()
        },
      },
    )
  }

  const error = createSession.error
  const message =
    error instanceof ApiError ? error.message : error ? 'Could not schedule that class.' : null

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title="Add a class to the timetable"
      description="One session. Use Generate a schedule for a class that repeats weekly."
      width="lg"
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() => form.submit(submit)}
            disabled={createSession.isPending}
          >
            {createSession.isPending ? 'Scheduling' : 'Schedule the class'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <ResourceField
          label="Class"
          placeholder="Choose a class"
          options={classes.data ?? []}
          getLabel={(item) => item.title}
          value={classId}
          onChange={setClassId}
          onBlur={() => form.touch('class_id')}
          error={form.error('class_id')}
        />

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
          <Field
            label="Length"
            hint="Leave blank to use the class default"
            error={form.error('duration_min')}
          >
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="number"
                inputMode="numeric"
                aria-describedby={describedBy}
                invalid={form.error('duration_min') !== null}
                onBlur={() => form.touch('duration_min')}
                value={duration}
                placeholder={chosenClass ? `${chosenClass.default_duration_min} minutes` : 'Minutes'}
                onChange={(event) => setDuration(event.target.value)}
              />
            )}
          </Field>
          <Field
            label="Capacity"
            hint="Leave blank to use the class default"
            error={form.error('capacity')}
          >
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="number"
                inputMode="numeric"
                aria-describedby={describedBy}
                invalid={form.error('capacity') !== null}
                onBlur={() => form.touch('capacity')}
                value={capacity}
                placeholder={chosenClass ? `${chosenClass.default_capacity} spots` : 'Spots'}
                onChange={(event) => setCapacity(event.target.value)}
              />
            )}
          </Field>
        </div>

        {form.blocked && (
          <p role="alert" className="text-14 text-bad-ink">
            Nothing was scheduled. Check the fields marked above.
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
