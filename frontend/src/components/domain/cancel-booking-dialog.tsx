import { useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextArea } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { useCancelBooking } from '@/hooks/use-bookings'
import { spotNoun } from '@/lib/vocabulary'
import { LIMITS, maxLength } from '@/lib/validation'
import type { BookingStatus, Uuid } from '@/api/types'

export interface CancelTarget {
  bookingId: Uuid
  memberName: string
  status: BookingStatus
  className: string
  discipline: string
}

/**
 * Cancel a booking.
 *
 * The confirmation is worth the extra click for one reason: cancelling a booked
 * place can hand it to somebody else, immediately and irreversibly. The dialog
 * says so before the click, and the toast afterwards names whoever got it —
 * because from the seat count alone a spot that was refilled looks exactly like
 * one that was not, and the person at the desk is the one who has to tell
 * somebody they are in.
 *
 * Leaving the waiting list is the quieter case and says so: nothing is freed and
 * nobody moves up into a place that does not exist.
 */
export function CancelBookingDialog({
  target,
  onClose,
  onPromoted,
}: {
  target: CancelTarget | null
  onClose: () => void
  /** Lets the roster wash the promoted row once — the app's one animated moment. */
  onPromoted?: (bookingId: Uuid) => void
}) {
  const { notify } = useToast()
  const cancelBooking = useCancelBooking()
  const [note, setNote] = useState('')

  const form = useForm({ note: maxLength(note, LIMITS.bookingNote) })

  function close() {
    onClose()
    setNote('')
    cancelBooking.reset()
  }

  if (target === null) return null

  const wasWaiting = target.status === 'waitlisted'

  return (
    <Dialog
      open
      onOpenChange={(next) => !next && close()}
      title={wasWaiting ? 'Take off the waiting list' : 'Cancel this booking'}
      description={
        wasWaiting
          ? `${target.memberName} will no longer be waiting for a ${spotNoun(target.discipline, false)} on ${target.className}.`
          : `The ${spotNoun(target.discipline, false)} opens immediately, and goes to the top of the waiting list if anyone is on it.`
      }
      footer={
        <>
          <Button onClick={close}>Keep the booking</Button>
          <Button
            variant="danger"
            disabled={cancelBooking.isPending}
            onClick={() =>
              form.submit(() =>
                cancelBooking.mutate(
                { bookingId: target.bookingId, note: note.trim() || undefined },
                {
                  onSuccess: (result) => {
                    if (result.promoted) {
                      notify('Cancelled, and the spot was filled', {
                        tone: 'wait',
                        detail: `${result.promoted.member.full_name} was at the top of the waiting list and now has it.`,
                      })
                      onPromoted?.(result.promoted.id)
                    } else {
                      notify('Cancelled', {
                        detail: wasWaiting
                          ? `${target.memberName} is off the waiting list.`
                          : `A ${spotNoun(target.discipline, false)} is free on ${target.className}.`,
                      })
                    }
                    close()
                    },
                  },
                ),
              )
            }
          >
            {cancelBooking.isPending
              ? 'Cancelling'
              : wasWaiting
                ? 'Take them off'
                : 'Cancel the booking'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <Field
          label="Note"
          hint="Optional. Becomes a permanent entry in this booking's history."
          error={form.error('note')}
        >
          {(id, describedBy) => (
            <TextArea
              id={id}
              aria-describedby={describedBy}
              autoFocus
              value={note}
              onChange={(event) => setNote(event.target.value)}
              onBlur={() => form.touch('note')}
              placeholder="Why, if it is worth recording"
            />
          )}
        </Field>

        {cancelBooking.error && (
          <p role="alert" className="text-14 text-bad-ink">
            {cancelBooking.error instanceof ApiError
              ? cancelBooking.error.message
              : 'Could not cancel that booking.'}
          </p>
        )}
      </div>
    </Dialog>
  )
}
