import { Link, NavLink, Outlet } from 'react-router-dom'
import { useCurrentUser, useSignOut } from '@/hooks/use-auth'
import { cn } from '@/lib/cn'
import { routes } from '@/lib/routes'

/**
 * The member's side of the building.
 *
 * A different shell rather than the studio one with items hidden, and the reason
 * is structural rather than cosmetic: `AppShell` mounts `StudioProvider`, which
 * fetches the dashboard to establish the studio's timezone — and a member is
 * refused that endpoint. Reusing it would mean a shell whose first act is a 403.
 *
 * It needs no timezone of its own either. Every date and time a member sees
 * arrives from the server already converted to the studio's local wall clock,
 * and whether a class has passed is a boolean the server computed. There is no
 * date arithmetic on this side at all, which is the right answer for screens
 * somebody will open on a phone in another timezone.
 *
 * Two destinations, so the navigation is a pair of links rather than a rail. A
 * sidebar for two items would be furniture.
 */
export function MemberShell() {
  const user = useCurrentUser()
  const signOut = useSignOut()

  return (
    <div className="min-h-screen bg-paper">
      <header className="border-b border-hairline">
        <div className="mx-auto flex max-w-[900px] flex-wrap items-center justify-between gap-x-8 gap-y-4 px-6 py-5 sm:px-8">
          <Link
            to={routes.myBookings}
            className="display whitespace-nowrap text-24 leading-none transition-colors duration-[120ms] hover:text-ink"
          >
            Mornington Studios
          </Link>

          <nav className="flex items-center gap-7">
            <MemberLink to={routes.mySchedule}>Classes</MemberLink>
            <MemberLink to={routes.myBookings}>My bookings</MemberLink>
          </nav>

          <div className="flex items-center gap-5">
            <span className="hidden text-12 text-graphite sm:inline">{user.full_name}</span>
            <button
              type="button"
              onClick={() => signOut.mutate()}
              className="text-12 text-graphite transition-colors duration-[120ms] hover:text-ink"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[900px] px-6 py-10 sm:px-8 sm:py-14">
        <Outlet />
      </main>
    </div>
  )
}

/** A navigation link that marks where you are with weight, not a box. */
function MemberLink({ to, children }: { to: string; children: string }) {
  return (
    <NavLink
      to={to}
      end
      className={({ isActive }) =>
        cn(
          'text-14 transition-colors duration-[120ms] hover:text-ink',
          isActive ? 'font-medium text-ink' : 'text-graphite',
        )
      }
    >
      {children}
    </NavLink>
  )
}
