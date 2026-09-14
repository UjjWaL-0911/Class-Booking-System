import { Link, NavLink } from 'react-router-dom'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { useCurrentUser, useSignOut } from '@/hooks/use-auth'
import { useMyMembership } from '@/hooks/use-me'
import { cn } from '@/lib/cn'
import { routes } from '@/lib/routes'

/**
 * The member's navigation, built like the studio's and standing in the page
 * rather than on top of it.
 *
 * It began as a header bar because there were two destinations and a rail for two
 * items is furniture. With four it is the right shape — and matching the studio's
 * chrome exactly is worth more than a member-specific look would be: it is one
 * product, and somebody who is both a customer and a colleague should not have to
 * learn two interfaces.
 *
 * The membership line at the bottom is the one thing this rail has that the
 * studio's does not, and it is only ever shown when it has something to say. A
 * lapsed membership is the explanation for a refusal the member is about to meet
 * on the next screen, so it follows them between screens rather than living on
 * one of them.
 */
const LINKS = [
  { to: routes.myBookings, label: 'My bookings', end: true },
  { to: routes.myTimetable, label: 'Timetable', end: false },
  { to: routes.myClasses, label: 'Classes', end: false },
]

export function MemberRail() {
  const user = useCurrentUser()
  const signOut = useSignOut()
  const membership = useMyMembership()

  return (
    <nav
      aria-label="Sections"
      className="flex w-[304px] shrink-0 flex-col justify-between px-7 py-10"
    >
      <div className="flex flex-col gap-12">
        <div>
          <Link
            to={routes.myBookings}
            className="display inline-block whitespace-nowrap text-28 transition-colors duration-[120ms] hover:text-ink"
          >
            Mornington Studios
          </Link>
          <p className="tracked mt-1 text-11 text-graphite">Member</p>
        </div>

        <ul className="flex flex-col gap-1">
          {LINKS.map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.end}
                className={({ isActive }) =>
                  cn(
                    'group flex items-center gap-3 py-1.5 text-12 transition-colors duration-[120ms]',
                    isActive ? 'font-medium text-ink' : 'text-graphite hover:text-ink',
                  )
                }
              >
                {({ isActive }) => (
                  <>
                    <span
                      aria-hidden="true"
                      className={cn(
                        'h-px shrink-0 transition-all duration-[120ms]',
                        isActive ? 'w-6 bg-brass' : 'w-4 bg-transparent group-hover:bg-mute',
                      )}
                    />
                    <span className="tracked flex-1">{link.label}</span>
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-4">
        {membership.data?.is_expired && (
          <p className="max-w-[30ch] text-11 leading-[1.5] text-bad-ink">
            Your membership has lapsed. Renew at the front desk to book again.
          </p>
        )}
        <ThemeToggle />
        <div className="flex flex-col gap-1">
          <p className="text-12 font-medium">{user.full_name}</p>
          <button
            type="button"
            onClick={() => signOut.mutate()}
            disabled={signOut.isPending}
            className="tracked self-start text-11 text-graphite underline-offset-4 hover:text-ink hover:underline disabled:text-mute"
          >
            {signOut.isPending ? 'Signing out' : 'Sign out'}
          </button>
        </div>
      </div>
    </nav>
  )
}
