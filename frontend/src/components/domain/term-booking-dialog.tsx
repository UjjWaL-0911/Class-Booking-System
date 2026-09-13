import { useEffect, useState } from 'react'
import { MemberPicker } from './member-picker'
import { WeekdayChooser } from './weekday-chooser'
import { TermBookingReportView } from './term-booking-report'
import { ResourceField } from './resource-field'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextArea, TextInput } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { useBookTerm } from '@/hooks/use-bookings'
import { useClasses } from '@/hooks/use-classes'
import { useStudio } from '@/studio/studio-context'
import { addDays } from '@/lib/dates'
import { chosen, dateChosen, firstProblem, LIMITS, maxLength, notBefore } from '@/lib/validation'
import type { Member, TermBookingReport } from '@/api/types'

/**
 * Book one member into a whole term of a class.
 *
 * Not one of the ten goals. It is the same shape as generating a recurring
 * schedule — pick a pattern, get a report of what happened — because it has the
 * same problem: a bulk action over candidates that can each fail individually.
 *
 * **The report stays on screen after it runs.** That is the whole feature. Booking
 * fourteen weeks and being told "Done" would leave somebody to go and check
 * whether the fourth week waitlisted, and the person at the desk usually has the
 * member on the phone while they do it.
 *
 * Weekdays are optional and filter sessions that already exist — this never
 * creates one. A member joining a Monday/Wednesday class mid-term wants the
 * Mondays and Wednesdays already on the timetable.
 */
export function TermBookingDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { today } = useStudio()
  const { notify } = useToast()
  const classes = useClasses()
  const bookTerm = useBookTerm()

  const [member, setMember] = useState<Member | null>(null)
  const [classId, setClassId] = useState('')
  const [from, setFrom] = useState(today)
  const [to, setTo] = useState(addDays(today, 84))
  const [weekdays, setWeekdays] = useState<number[]>([])
  const [note, setNote] = useState('')
  const [report, setReport] = useState<TermBookingReport | null>(null)

  const form = useForm({
    member_id: chosen(member?.id ?? '', 'a member'),
    class_id: chosen(classId, 'a class'),
    date_from: dateChosen(from, 'a start date'),
    date_to: firstProblem(
      dateChosen(to, 'an end date'),
      notBefore(to, from, 'the end of the term'),
    ),
    note: maxLength(note, LIMITS.bookingNote),
  })
  const { reset: resetForm } = form

  useEffect(() => {
    if (!open) return
    setMember(null)
    setClassId('')
    setFrom(today)
    setTo(addDays(today, 84))
    setWeekdays([])
    setNote('')
    setReport(null)
    resetForm()
  }, [open, today, resetForm])

  function close() {
    onOpenChange(false)
    bookTerm.reset()
  }

  function submit() {
    bookTerm.mutate(
      {
        member_id: member?.id ?? '',
        class_id: classId,
        date_from: from,
        date_to: to,
        weekdays: weekdays.length > 0 ? [...weekdays].sort((a, b) => a - b) : null,
        note: note.trim() || null,
      },
      {
        onSuccess: (result) => {
          setReport(result)
          notify(
            result.booked.length > 0 || result.waitlisted.length > 0
              ? `${result.booked.length + result.waitlisted.length} of ${result.requested} booked`
              : 'Nothing was booked',
            { tone: result.booked.length > 0 ? 'good' : 'wait' },
          )
        },
      },
    )
  }

  const message =
    bookTerm.error instanceof ApiError
      ? bookTerm.error.message
      : bookTerm.error
        ? 'Could not book that term.'
        : null

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title={report ? 'What was booked' : 'Book a term'}
      description={
        report
          ? undefined
          : 'One member, every session of a class in a date range. Sessions must already be on the timetable.'
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
              onClick={() => form.submit(submit)}
              disabled={bookTerm.isPending}
            >
              {bookTerm.isPending ? 'Booking' : 'Book the term'}
            </Button>
          </>
        )
      }
    >
      {report ? (
        <TermBookingReportView report={report} />
      ) : (
        <div className="flex flex-col gap-5">
          <MemberPicker selected={member} onSelect={setMember} autoFocus />
          {form.error('member_id') && (
            <p role="alert" className="-mt-3 text-12 text-bad-ink">
              {form.error('member_id')}
            </p>
          )}

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

          <WeekdayChooser value={weekdays} onChange={setWeekdays} />

          <Field
            label="Note"
            hint="Optional. Written onto every booking this makes."
            error={form.error('note')}
          >
            {(id, describedBy) => (
              <TextArea
                id={id}
                aria-describedby={describedBy}
                value={note}
                onChange={(event) => setNote(event.target.value)}
                onBlur={() => form.touch('note')}
              />
            )}
          </Field>

          {form.blocked && (
            <p role="alert" className="text-14 text-bad-ink">
              Nothing was booked. Check the fields marked above.
            </p>
          )}
          {message && (
            <p role="alert" className="text-14 text-bad-ink">
              {message}
            </p>
          )}
        </div>
      )}
    </Dialog>
  )
}
