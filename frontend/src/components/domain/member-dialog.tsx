import { useEffect, useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextArea, TextInput } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { useCreateMember, useUpdateMember } from '@/hooks/use-members'
import { useStudio } from '@/studio/studio-context'
import { addDays, daysBetween, expiryPhrase } from '@/lib/dates'
import { dateChosen, emailFormat, firstProblem, LIMITS, maxLength, required } from '@/lib/validation'
import type { Member } from '@/api/types'

/**
 * Add or edit a member (goal 1).
 *
 * One dialog for both, because the fields are identical and two components would
 * be two places for the validation to drift.
 *
 * The expiry field says what the date it holds means, live — "Expired 47 days
 * ago", "Expires in 3 days". A date input shows a date; what somebody at the desk
 * needs to know is whether that date is a problem, and recording a renewal is the
 * commonest reason this dialog is open.
 *
 * There is no HTML `maxlength` on these inputs, deliberately. A hard cap stops
 * the keystrokes and explains nothing — somebody pasting a long note just watches
 * it get cut off. The rule says what the limit is and how far over they are.
 *
 * Field errors come from two places and the local one wins. Where this form is
 * happy and the server is not — a duplicate address, say — the server's message
 * appears on the field it names.
 */
export function MemberDialog({
  open,
  onOpenChange,
  member,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** Absent when adding. */
  member?: Member | null
}) {
  const { today } = useStudio()
  const { notify } = useToast()
  const createMember = useCreateMember()
  const updateMember = useUpdateMember()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [expiry, setExpiry] = useState('')
  const [notes, setNotes] = useState('')

  const editing = member != null
  const mutation = editing ? updateMember : createMember

  const serverFields = (
    mutation.error instanceof ApiError ? mutation.error.details['fields'] : null
  ) as Record<string, string> | undefined | null

  const form = useForm({
    full_name: firstProblem(required(fullName, 'a full name'), maxLength(fullName, LIMITS.fullName)),
    email: emailFormat(email),
    membership_expiry: dateChosen(expiry, 'the date the membership runs until'),
    notes: maxLength(notes, LIMITS.memberNotes),
  })
  const { reset: resetForm } = form

  // Reset when the dialog opens rather than on every render of the parent: the
  // member being edited changes while the dialog is closed, and reading props
  // straight into state would strand the previous person's details in the form.
  useEffect(() => {
    if (!open) return
    setFullName(member?.full_name ?? '')
    setEmail(member?.email ?? '')
    // A year from today is the common case for a new membership, and a blank date
    // input is the one field people forget.
    setExpiry(member?.membership_expiry ?? addDays(today, 365))
    setNotes(member?.notes ?? '')
    resetForm()
  }, [open, member, today, resetForm])

  const phrase = expiry === '' ? null : expiryPhrase(daysBetween(today, expiry))

  /** The local rule if there is one, otherwise whatever the server said. */
  function problem(field: 'full_name' | 'email' | 'membership_expiry' | 'notes'): string | null {
    return form.error(field) ?? serverFields?.[field] ?? null
  }

  function close() {
    onOpenChange(false)
    createMember.reset()
    updateMember.reset()
  }

  function save() {
    const body = {
      full_name: fullName.trim(),
      email: email.trim(),
      membership_expiry: expiry,
      notes: notes.trim(),
    }

    if (editing) {
      updateMember.mutate(
        { id: member.id, body },
        {
          onSuccess: (saved) => {
            notify('Saved', { detail: `${saved.full_name}’s record is up to date.` })
            close()
          },
        },
      )
    } else {
      createMember.mutate(body, {
        onSuccess: (saved) => {
          notify('Added', { tone: 'good', detail: `${saved.full_name} can now be booked in.` })
          close()
        },
      })
    }
  }

  // Only shown when the server's complaint is not already sitting on a field.
  const message =
    serverFields || !mutation.error
      ? null
      : mutation.error instanceof ApiError
        ? mutation.error.message
        : 'Could not save that member.'

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title={editing ? 'Edit this member' : 'Add a member'}
      description={
        editing
          ? undefined
          : 'Members do not sign in. This is the record the desk books classes against.'
      }
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button variant="primary" onClick={() => form.submit(save)} disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving' : editing ? 'Save changes' : 'Add the member'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <Field label="Full name" error={problem('full_name')}>
          {(id, describedBy) => (
            <TextInput
              id={id}
              aria-describedby={describedBy}
              autoFocus
              invalid={problem('full_name') !== null}
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              onBlur={() => form.touch('full_name')}
            />
          )}
        </Field>

        <Field label="Email" error={problem('email')}>
          {(id, describedBy) => (
            <TextInput
              id={id}
              type="email"
              aria-describedby={describedBy}
              invalid={problem('email') !== null}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              onBlur={() => form.touch('email')}
            />
          )}
        </Field>

        <Field
          label="Membership runs until"
          hint={phrase ?? undefined}
          error={problem('membership_expiry')}
        >
          {(id, describedBy) => (
            <TextInput
              id={id}
              type="date"
              aria-describedby={describedBy}
              invalid={problem('membership_expiry') !== null}
              value={expiry}
              onChange={(event) => setExpiry(event.target.value)}
              onBlur={() => form.touch('membership_expiry')}
            />
          )}
        </Field>

        <Field
          label="Notes"
          hint="Injuries, preferences — anything the desk should know."
          error={problem('notes')}
        >
          {(id, describedBy) => (
            <TextArea
              id={id}
              aria-describedby={describedBy}
              value={notes}
              onChange={(event) => setNotes(event.target.value)}
              onBlur={() => form.touch('notes')}
            />
          )}
        </Field>

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
