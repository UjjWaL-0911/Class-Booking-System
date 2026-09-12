import { useState } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Field, TextInput } from '@/components/ui/field'
import { BootScreen } from '@/components/ui/states'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { useForm } from '@/hooks/use-form'
import { useSession, useSignIn } from '@/hooks/use-auth'
import { routes } from '@/lib/routes'
import { emailFormat, required } from '@/lib/validation'

/**
 * Sign in (goal 1).
 *
 * Three details that are not decoration. The form posts on submit rather than
 * from a click handler, so Enter works from either field — a front desk signs in
 * dozens of times a week and never reaches for the mouse. `noValidate` turns off
 * the browser's own bubble so there is one voice telling somebody what is wrong,
 * ours, in the same place as every other message in the app. And the sign-in
 * error is whatever the server said: a rate limit arrives here as its own
 * sentence with its own wait, and replacing it with "Incorrect email or password"
 * would leave somebody retyping a correct password into a locked window.
 */
export function SignInPage() {
  const { status } = useSession()
  const location = useLocation()
  const navigate = useNavigate()
  const signIn = useSignIn()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')

  const form = useForm({
    email: emailFormat(email),
    password: required(password, 'your password'),
  })

  // `unknown` means the session restore has not answered yet. Treating it as
  // signed-out would show the form to somebody who is already in, for exactly as
  // long as the round trip takes.
  if (status === 'unknown') return <BootScreen>Just a moment</BootScreen>

  if (status === 'signed-in') {
    const from = (location.state as { from?: string } | null)?.from
    return <Navigate to={from ?? routes.today} replace />
  }

  const error = signIn.error
  const message = error instanceof ApiError ? error.message : error ? 'Could not sign in.' : null

  return (
    <div className="flex min-h-screen items-center justify-center bg-paper px-6 py-12">
      <div className="w-full max-w-[380px]">
        <div className="mb-8">
          <Link to={routes.landing} className="display text-36 hover:text-ink">
            Mornington
          </Link>
          <p className="mt-1 text-14 text-graphite">
            Sign in to take bookings and manage the timetable.
          </p>
        </div>

        <form
          noValidate
          className="flex flex-col gap-5"
          onSubmit={(event) => {
            event.preventDefault()
            form.submit(() =>
              signIn.mutate(
                { email: email.trim(), password },
                { onSuccess: () => navigate(routes.today, { replace: true }) },
              ),
            )
          }}
        >
          <Field label="Email" error={form.error('email')}>
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="email"
                aria-describedby={describedBy}
                autoComplete="username"
                autoFocus
                invalid={form.error('email') !== null}
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                onBlur={() => form.touch('email')}
              />
            )}
          </Field>

          <Field label="Password" error={form.error('password')}>
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="password"
                aria-describedby={describedBy}
                autoComplete="current-password"
                invalid={form.error('password') !== null}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onBlur={() => form.touch('password')}
              />
            )}
          </Field>

          {message && (
            <p role="alert" className="text-14 text-bad-ink">
              {message}
            </p>
          )}

          <Button type="submit" variant="primary" disabled={signIn.isPending} className="mt-1">
            {signIn.isPending ? 'Signing in' : 'Sign in'}
          </Button>
        </form>

        <div className="mt-6 w-[168px]">
          <ThemeToggle />
        </div>

        {/* The demo accounts, on the screen that needs them. A reviewer opening a
            deployed link should not have to find the README to get in. */}
        <div className="mt-6 flex flex-col gap-1.5 px-1 text-11 text-graphite">
          <p className="font-medium text-ink">Demo accounts</p>
          <p>manager@studio.demo and frontdesk@studio.demo are studio staff.</p>
          <p>priya@studio.demo teaches, and sees only her own classes.</p>
          <p>The password for all of them is StudioDemo!2026</p>
        </div>
      </div>
    </div>
  )
}
