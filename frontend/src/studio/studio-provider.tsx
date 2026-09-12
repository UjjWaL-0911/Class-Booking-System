import type { ReactNode } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDashboard } from '@/api/insights'
import { keys } from '@/lib/query-keys'
import { StudioContext } from './studio-context'

/**
 * Establishes the studio's clock before anything below it renders.
 *
 * The timezone arrives with the dashboard rather than from an endpoint of its
 * own: the dashboard is the first screen, every signed-in user can read it, and
 * asking the server for the same fact twice would be the more expensive design.
 *
 * Blocking on it is deliberate. Every date and time on every screen underneath is
 * formatted against this value, and rendering a table of timestamps in the
 * viewer's timezone for a second before correcting them is worse than waiting for
 * one request.
 */
export function StudioProvider({
  children,
  fallback,
  onError,
}: {
  children: ReactNode
  fallback: ReactNode
  onError: (error: unknown) => ReactNode
}) {
  const query = useQuery({
    queryKey: keys.dashboard,
    queryFn: getDashboard,
    // Longer than the default: this is the screen's data *and* the app's clock,
    // and the clock does not need refetching every twenty seconds. Writes
    // invalidate it explicitly when the numbers actually change.
    staleTime: 60_000,
  })

  if (query.isPending) return <>{fallback}</>
  if (query.error) return <>{onError(query.error)}</>

  const dashboard = query.data
  return (
    <StudioContext.Provider
      value={{ timeZone: dashboard.timezone, today: dashboard.as_of, dashboard }}
    >
      {children}
    </StudioContext.Provider>
  )
}
