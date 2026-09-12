import { useState } from 'react'
import { ApiError } from '@/api/errors'
import { MemberPicker } from './member-picker'
import { Occupancy } from './occupancy-mark'
import { SessionPicker } from './session-picker'
import { spotNoun } from '@/lib/vocabulary'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextArea } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { useCreateBooking } from '@/hooks/use-bookings'
import { formatDateShort, formatTime } from '@/lib/dates'
import { LIMITS, maxLength } from '@/lib/validation'
import type { Member, Session } from '@/api/types'

/**
 * Take a booking (goal 4).
 *
 * The dialog never predicts the outcome. It says "Book a member", and the server
 * decides — under a row lock on the session — whether that is a spot or a place
 * in the queue. So the button does not say "Add to waiting list" even when the
 * class looks full on screen: between rendering and clicking, somebody may have
 * cancelled, and the honest label is the one that is true either way.
 *
 * What the dialog *does* do is put the two commonest rejections in front of
 * somebody before they click: how full the class is, and whether the member's
 * membership has lapsed. Both pickers carry that on every row, which is the whole
 * reason neither of them is a dropdown.
 */
export function TakeBookingDialog({
  open,
  onOpenChange,
  session,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Locked when opened from a session; chosen from the picker otherwise. */
  session?: Session
}) {
  const { notify } = useToast()
  const createBooking = useCreateBooking()

  const [member, setMember] = useState<Member | null>(null)
  const [picked, setPicked] = useState<Session | null>(null)
  const [note, setNote] = useState('')

  const chosen = session ?? picked

  const form = useForm({
    session: chosen === null ? 'Choose a class.' : null,
    member: member === null ? 'Choose the member this booking is for.' : null,
    note: maxLength(note, LIMITS.bookingNote),
  })

  function close() {
    onOpenChange(false)
    setMember(null)
    setPicked(null)
    setNote('')
    createBooking.reset()
  }

  function submit() {
    if (!member || !chosen) return
    createBooking.mutate(
      { sessionId: chosen.id, memberId: member.id, note: note.trim() || undefined },
      {
        onSuccess: (booking) => {
          if (booking.status === 'waitlisted') {
            notify(`${member.full_name} is on the waiting list`, {
              tone: 'wait',
              detail: `${chosen.class_title} was full. They take the next ${spotNoun(chosen.discipline, false)} that opens.`,
            })
          } else {
            notify('Booked', {
              tone: 'good',
              detail: `${member.full_name} on ${chosen.class_title}, ${formatDateShort(chosen.session_date)} at ${formatTime(chosen.start_time)}.`,
            })
          }
          close()
        },
      },
    )
  }

  const error = createBooking.error
  const message =
    error instanceof ApiError ? error.message : error ? 'Could not take that booking.' : null

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title="Take a booking"
      description="The studio decides whether this is a place or a spot on the waiting list."
      width="xl"
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() => form.submit(submit)}
            disabled={createBooking.isPending}
          >
            {createBooking.isPending ? 'Booking' : 'Book a member'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <Field label="Class" error={session ? null : form.error('session')}>
          {() =>
            session ? (
              <LockedSession session={session} />
            ) : (
              <SessionPicker selected={picked} onSelect={setPicked} enabled={open} />
            )
          }
        </Field>

        <Field label="Member" error={form.error('member')}>
          {() => (
            <MemberPicker selected={member} onSelect={setMember} autoFocus={session !== undefined} />
          )}
        </Field>

        <Field
          label="Note"
          hint="Optional. Goes into the booking's history, where it cannot be edited later."
          error={form.error('note')}
        >
          {(id, describedBy) => (
            <TextArea
              id={id}
              aria-describedby={describedBy}
              value={note}
              onChange={(event) => setNote(event.target.value)}
              onBlur={() => form.touch('note')}
              placeholder="Anything the instructor should know"
            />
          )}
        </Field>

        {form.blocked && (
          <p role="alert" className="text-14 text-bad-ink">
            No booking was taken. Check the fields marked above.
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

/** Opened from a session page: the class is settled, so it is stated, not chosen. */
function LockedSession({ session }: { session: Session }) {
  return (
    <div className="flex items-center justify-between gap-4 rounded-sm border border-rule bg-paper px-3.5 py-3">
      <div className="flex min-w-0 flex-col">
        <span className="text-14 font-medium">{session.class_title}</span>
        <span className="text-11 text-graphite">
          {formatDateShort(session.session_date)}, {formatTime(session.start_time)} in{' '}
          {session.room_name}
        </span>
      </div>
      <Occupancy session={session} className="shrink-0" />
    </div>
  )
}
