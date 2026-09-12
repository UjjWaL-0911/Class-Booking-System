import { useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { ResourceField } from './resource-field'
import { Field, TextInput } from '@/components/ui/field'
import { useClasses, useRooms } from '@/hooks/use-classes'
import { useForm } from '@/hooks/use-form'
import { useGenerateSessions } from '@/hooks/use-sessions'
import { useTeachers } from '@/hooks/use-users'
import { GenerationReportView } from './generation-report'
import { addDays } from '@/lib/dates'
import { chosen, dateChosen, firstProblem, notBefore } from '@/lib/validation'
import { cn } from '@/lib/cn'
import type { LocalDate } from '@/api/types'

/** Monday is 0, matching the API and the studio's week. */
const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']


/**
 * Generate a weekly schedule (goal 7).
 *
 * The dialog has two halves, and the second one is the feature. Goal 7 asks for a
 * result that "reports which sessions were created and which were skipped because
 * the chosen instructor or room was already booked in an overlapping window" — so
 * the report stays on screen after the run, with every skipped date named and the
 * reason beside it. Closing it is a deliberate act, not a toast that vanishes
 * while somebody is still reading the third line.
 *
 * The third skip reason is not in the brief and is worth keeping: on the night the
 * clocks go forward a 01:30 class has no 01:30 to start at. It is reported rather
 * than quietly shifted an hour.
 */
export function GenerateScheduleDialog({
  open,
  onOpenChange,
  defaultDate,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  defaultDate: LocalDate
}) {
  const classes = useClasses()
  const rooms = useRooms()
  const teachers = useTeachers()
  const generate = useGenerateSessions()

  const [classId, setClassId] = useState('')
  const [instructorId, setInstructorId] = useState('')
  const [roomId, setRoomId] = useState('')
  const [time, setTime] = useState('18:00')
  const [weekdays, setWeekdays] = useState<number[]>([])
  const [from, setFrom] = useState(defaultDate)
  const [to, setTo] = useState(addDays(defaultDate, 27))

  const report = generate.data

  const form = useForm({
    class_id: chosen(classId, 'a class'),
    primary_instructor_id: chosen(instructorId, 'who is teaching'),
    room_id: chosen(roomId, 'a room'),
    start_time: dateChosen(time, 'a start time'),
    weekdays: weekdays.length === 0 ? 'Pick at least one day of the week.' : null,
    date_from: dateChosen(from, 'a start date'),
    date_to: firstProblem(dateChosen(to, 'an end date'), notBefore(to, from, 'the start date')),
  })

  function close() {
    onOpenChange(false)
    generate.reset()
    setWeekdays([])
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title={report ? 'Schedule generated' : 'Generate a weekly schedule'}
      description={
        report
          ? undefined
          : 'The same class, instructor, room and time, repeated on the days you choose.'
      }
      width="lg"
      footer={
        report ? (
          <Button variant="primary" onClick={close}>
            Done
          </Button>
        ) : (
          <>
            <Button onClick={close}>Cancel</Button>
            <Button
              variant="primary"
              disabled={generate.isPending}
              onClick={() =>
                form.submit(() =>
                  generate.mutate({
                    class_id: classId,
                    primary_instructor_id: instructorId,
                    room_id: roomId,
                    start_time: `${time}:00`,
                    weekdays: [...weekdays].sort((a, b) => a - b),
                    date_from: from,
                    date_to: to,
                  }),
                )
              }
            >
              {generate.isPending ? 'Generating' : 'Generate the schedule'}
            </Button>
          </>
        )
      }
    >
      {report ? <GenerationReportView report={report} /> : (
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

          <Field label="Days" error={form.error('weekdays')}>
            {() => (
              <div className="flex flex-wrap gap-1.5">
                {WEEKDAYS.map((label, index) => {
                  const on = weekdays.includes(index)
                  return (
                    <button
                      key={label}
                      type="button"
                      aria-pressed={on}
                      onClick={() =>
                        setWeekdays((current) =>
                          current.includes(index)
                            ? current.filter((day) => day !== index)
                            : [...current, index],
                        )
                      }
                      className={cn(
                        'h-8 w-12 rounded-sm border text-12 font-medium transition-colors duration-[120ms]',
                        on
                          ? 'border-ink bg-ink text-paper'
                          : 'border-rule bg-card text-graphite hover:border-mute hover:text-ink',
                      )}
                    >
                      {label}
                    </button>
                  )
                })}
              </div>
            )}
          </Field>

          <div className="grid grid-cols-3 gap-4">
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
            <Field label="From" error={form.error('date_from')}>
              {(id, describedBy) => (
                <TextInput
                  id={id}
                  type="date"
                  aria-describedby={describedBy}
                  invalid={form.error('date_from') !== null}
                  value={from}
                  onChange={(event) => setFrom(event.target.value)}
                  onBlur={() => form.touch('date_from')}
                />
              )}
            </Field>
            <Field label="Until" error={form.error('date_to')}>
              {(id, describedBy) => (
                <TextInput
                  id={id}
                  type="date"
                  aria-describedby={describedBy}
                  invalid={form.error('date_to') !== null}
                  value={to}
                  onChange={(event) => setTo(event.target.value)}
                  onBlur={() => form.touch('date_to')}
                />
              )}
            </Field>
          </div>

          {form.blocked && (
            <p role="alert" className="text-14 text-bad-ink">
              Nothing was generated. Check the fields marked above.
            </p>
          )}

          {generate.error && (
            <p role="alert" className="text-14 text-bad-ink">
              {generate.error instanceof ApiError
                ? generate.error.message
                : 'Could not generate that schedule.'}
            </p>
          )}
        </div>
      )}
    </Dialog>
  )
}
