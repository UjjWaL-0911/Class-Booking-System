import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useSession } from '@/hooks/use-auth'
import { BootScreen } from '@/components/ui/states'
import { routes } from '@/lib/routes'

/**
 * The gate in front of every signed-in route.
 *
 * This is a convenience, not a security boundary. Every endpoint behind it checks
 * the caller's role itself — goal 1 requires the difference to be enforced on the
 * server, "not just hidden in the interface" — so removing this component would
 * make the app unpleasant to use and would not grant anyone a single row they
 * could not already read.
 *
 * The `unknown` state is why this is not a one-line redirect: on a fresh load the
 * app does not yet know whether there is a session, and treating "don't know" as
 * "signed out" flashes the login form at somebody who is already signed in.
 */
export function RequireSession() {
  const { status } = useSession()
  const location = useLocation()

  if (status === 'unknown') return <BootScreen>Just a moment</BootScreen>

  if (status === 'signed-out') {
    // Where they were going, so signing in finishes the journey rather than
    // dropping them on the home screen.
    return <Navigate to={routes.signIn} replace state={{ from: location.pathname }} />
  }

  return <Outlet />
}
