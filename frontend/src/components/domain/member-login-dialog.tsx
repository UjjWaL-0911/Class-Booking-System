import { useEffect, useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextInput } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useEnableMemberLogin } from '@/hooks/use-members'
import { LIMITS } from '@/lib/validation'
import type { Member } from '@/api/types'

/**
 * Letting one member book for themselves.
 *
 * **There is no sign-up page, and this dialog is the reason there does not need
 * to be one.** A member account implies a membership, a membership implies
 * somebody paid, and a form on the open internet cannot know that — so it would
 * either hand out memberships nobody agreed to, or create accounts that can do
 * nothing until the desk intervenes anyway. Somebody already inside vouches
 * instead, which is the same argument that keeps staff registration closed.
 *
 * **It does not grant a membership**, and the dialog says so where somebody can
 * read it. Whether this person may book is still decided by their expiry date, so
 * switching on a login for a lapsed member gives them a working sign-in and a
 * refusal at the point of booking. That is correct rather than an edge case, and
 * it is the whole reason this feature needed no notion of payment.
 *
 * The password is typed here and handed over in conversation, the same genuine
 * limitation as a colleague's account: there is no mail sender, so an invitation
 * has nothing to travel on.
 */
export function MemberLoginDialog({
  member,
  onClose,
}: {
  member: Member | null
  onClose: () => void
}) {
  const { notify } = useToast()
  const enable = useEnableMemberLogin()
  const [password, setPassword] = useState('')
  const [touched, setTouched] = useState(false)

  useEffect(() => {
    if (!member) return
    setPassword('')
    setTouched(false)
    enable.reset()
    // Depending on the mutation would reset the field under somebody mid-type.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [member])

  const tooShort = password.length < LIMITS.password
  const problem = touched && tooShort ? `At least ${LIMITS.password} characters.` : null

  function save() {
    setTouched(true)
    if (!member || tooShort) return
    enable.mutate(
      { id: member.id, password },
      {
        onSuccess: (updated) => {
          notify('They can sign in now', {
            tone: 'good',
            detail: `${updated.full_name} can book for themselves with ${updated.email}. Tell them the password you set.`,
          })
          onClose()
        },
      },
    )
  }

  const failed = enable.error
    ? enable.error instanceof ApiError
      ? enable.error.message
      : 'Could not switch that on.'
    : null

  return (
    <Dialog
      open={member !== null}
      onOpenChange={(next) => !next && onClose()}
      title={member ? `Let ${member.full_name} book online` : 'Let them book online'}
      description="They sign in with the email already on their record. Tell them the password in person — there is no email being sent."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save} disabled={enable.isPending}>
            {enable.isPending ? 'Switching on' : 'Switch it on'}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-5">
        <Field
          label="Password"
          hint={`At least ${LIMITS.password} characters. They cannot change it from inside the app yet.`}
          error={problem}
        >
          {(id, describedBy) => (
            <TextInput
              id={id}
              type="password"
              autoComplete="new-password"
              autoFocus
              aria-describedby={describedBy}
              invalid={problem !== null}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onBlur={() => setTouched(true)}
            />
          )}
        </Field>

        {/* Said here rather than discovered later. An account and a membership are
            different things, and the desk is the one who will be asked why a
            member who "has a login now" still cannot book. */}
        <p className="text-12 leading-[1.6] text-graphite">
          This gives them an account, not a membership. Whether they can book is still
          decided by their expiry date — if it has lapsed they will be able to sign in and
          see the timetable, and bookings will be refused until you renew it.
        </p>

        {failed && (
          <p role="alert" className="text-14 text-bad-ink">
            {failed}
          </p>
        )}
      </div>
    </Dialog>
  )
}
