import { useEffect, useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextInput } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { RoleChoice } from '@/components/domain/role-choice'
import { useCreateUser } from '@/hooks/use-users'
import { toMinor } from '@/lib/money'
import { emailFormat, firstProblem, LIMITS, maxLength, minLength, required } from '@/lib/validation'
import type { UserRole } from '@/api/types'

/**
 * Add a colleague — a member of staff, or an instructor.
 *
 * There is no edit here and no delete. Editing somebody's role or name is a
 * different job with different rules, and an account is deactivated rather than
 * removed because an instructor who leaves still has sessions and booking history
 * that must stay intact. Neither has an endpoint yet, and a button that pretends
 * otherwise is worse than its absence.
 *
 * The password is typed by whoever is adding the person and handed over in
 * conversation. That is a real limitation rather than a preference: there is no
 * mail sender, so an invitation link has nothing to travel on, and there is no
 * change-your-password screen yet either. The form says so plainly rather than
 * leaving somebody to discover it.
 */
export function PersonDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const { notify } = useToast()
  const createUser = useCreateUser()

  const [fullName, setFullName] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<UserRole>('instructor')
  const [password, setPassword] = useState('')
  const [rate, setRate] = useState('')

  const serverFields = (
    createUser.error instanceof ApiError ? createUser.error.details['fields'] : null
  ) as Record<string, string> | undefined | null

  const form = useForm({
    full_name: firstProblem(required(fullName, 'a full name'), maxLength(fullName, LIMITS.fullName)),
    email: emailFormat(email),
    password: firstProblem(
      required(password, 'a password'),
      minLength(password, LIMITS.password, 'A password'),
    ),
    // Empty is valid and means "not agreed yet". Only nonsense is a problem.
    session_rate_minor:
      toMinor(rate) === undefined
        ? 'Use digits and at most two decimal places, like 1200 or 1200.50.'
        : null,
  })
  const { reset: resetForm } = form

  useEffect(() => {
    if (!open) return
    setFullName('')
    setEmail('')
    setRole('instructor')
    setPassword('')
    setRate('')
    resetForm()
  }, [open, resetForm])

  function problem(field: 'full_name' | 'email' | 'password' | 'session_rate_minor'): string | null {
    return form.error(field) ?? serverFields?.[field] ?? null
  }

  function close() {
    onOpenChange(false)
    createUser.reset()
  }

  function save() {
    createUser.mutate(
      {
        full_name: fullName.trim(),
        email: email.trim(),
        role,
        password,
        session_rate_minor: toMinor(rate) ?? null,
      },
      {
        onSuccess: (person) => {
          notify('Added', {
            tone: 'good',
            detail:
              person.role === 'instructor'
                ? `${person.full_name} can now be put in front of a class.`
                : `${person.full_name} can sign in and run the desk.`,
          })
          close()
        },
      },
    )
  }

  const message =
    serverFields || !createUser.error
      ? null
      : createUser.error instanceof ApiError
        ? createUser.error.message
        : 'Could not add that person.'

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title="Add a person"
      description="They will be able to sign in straight away with the password you set here."
      footer={
        <>
          <Button onClick={close}>Cancel</Button>
          <Button
            variant="primary"
            onClick={() => form.submit(save)}
            disabled={createUser.isPending}
          >
            {createUser.isPending ? 'Adding' : 'Add the person'}
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

        <Field label="Email" hint="This is what they sign in with." error={problem('email')}>
          {(id, describedBy) => (
            <TextInput
              id={id}
              type="email"
              autoComplete="off"
              aria-describedby={describedBy}
              invalid={problem('email') !== null}
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              onBlur={() => form.touch('email')}
            />
          )}
        </Field>

        {/* Radios rather than a dropdown. Two options, and the difference between
            them is the most consequential thing on this form — a closed select
            hides the choice behind a click and shows only what was picked. */}
        <Field label="What they do">
          {(id, describedBy) => (
            <div id={id} aria-describedby={describedBy} className="flex flex-col gap-2.5 pt-1">
              <RoleChoice
                value="instructor"
                current={role}
                onChange={setRole}
                label="Instructor"
                detail="Sees only the sessions they lead or help with, and records attendance on them."
              />
              <RoleChoice
                value="staff"
                current={role}
                onChange={setRole}
                label="Studio staff"
                detail="Runs the whole studio: classes, sessions, members and every booking."
              />
            </div>
          )}
        </Field>

        {/* Optional, and deliberately after the role: somebody adding an
            instructor on a Monday morning should not be held up by a number that
            has to come from whoever agrees rates. An empty box means "not agreed",
            which the payroll report reports as such rather than as unpaid. */}
        <Field
          label="Per session"
          hint="Optional. What they are paid to lead one class — leave it empty until a rate is agreed."
          error={problem('session_rate_minor')}
        >
          {(id, describedBy) => (
            <TextInput
              id={id}
              inputMode="decimal"
              placeholder="No rate set"
              aria-describedby={describedBy}
              invalid={problem('session_rate_minor') !== null}
              value={rate}
              onChange={(event) => setRate(event.target.value)}
              onBlur={() => form.touch('session_rate_minor')}
            />
          )}
        </Field>

        <Field
          label="Password"
          hint={`At least ${LIMITS.password} characters. Tell them what you set — they cannot change it from inside the app yet.`}
          error={problem('password')}
        >
          {(id, describedBy) => (
            <TextInput
              id={id}
              type="password"
              autoComplete="new-password"
              aria-describedby={describedBy}
              invalid={problem('password') !== null}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              onBlur={() => form.touch('password')}
            />
          )}
        </Field>

        {form.blocked && (
          <p role="alert" className="text-14 text-bad-ink">
            Nobody was added. Check the fields marked above.
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
