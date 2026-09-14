import { Navigate, Outlet } from 'react-router-dom'
import { homeFor, useSession } from '@/hooks/use-auth'

/**
 * Keeps each role on its own side of the app.
 *
 * **Routing, not security.** Every endpoint decides for itself — a member calling
 * a studio route gets a 403 from the server, and the member routes resolve the
 * member from the credential rather than from anything in the URL. Deleting this
 * component would make the app confusing to use and would not hand anybody a
 * single row they could not already read. Goal 1 requires that difference to be
 * enforced on the server, "not just hidden in the interface", and it is.
 *
 * What it actually prevents is a worse experience: a member who bookmarked `/app`
 * would otherwise land on a shell whose first act is to fetch the dashboard and
 * be refused. Sending them home is a better answer than an error page.
 */
export function RequireStudio() {
  const { user } = useSession()
  if (user?.role === 'member') return <Navigate to={homeFor(user.role)} replace />
  return <Outlet />
}

export function RequireMember() {
  const { user } = useSession()
  if (user !== null && user.role !== 'member') return <Navigate to={homeFor(user.role)} replace />
  return <Outlet />
}
