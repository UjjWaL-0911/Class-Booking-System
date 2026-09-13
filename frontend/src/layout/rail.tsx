import { Link, NavLink } from 'react-router-dom'
import { ThemeToggle } from '@/components/ui/theme-toggle'
import { useAlertCount } from '@/hooks/use-alerts'
import { useCurrentUser, useSignOut } from '@/hooks/use-auth'
import { cn } from '@/lib/cn'
import { routes } from '@/lib/routes'

/**
 * Navigation, sitting *in* the page rather than on top of it.
 *
 * The rail used to have its own background and a border down its right edge,
 * which is what made it read as a separate panel pushed against the content — a
 * seam where there is no seam. Both are gone. It stands on the same ground as
 * everything else, and the only things marking it as navigation are that it is
 * over there and the words are small.
 *
 * The current item is a word in ink beside a short brass stroke. Not a filled
 * pill and not a bordered box: with no other boundaries on the screen a 2px mark
 * is more than enough to find, and anything heavier reintroduces exactly the box
 * this redesign removed.
 *
 * Tracked capitals, which this interface refuses everywhere else. Here they earn
 * their place — six words read as landmarks rather than as language, in the one
 * part of the page that is pure chrome. Still no icons: at this width the words
 * fit, and "Timetable" is unambiguous in a way that any glyph for it would not be.
 */
const LINKS = [
  { to: routes.today, label: 'Today' },
  { to: routes.timetable, label: 'Timetable' },
  { to: routes.bookings, label: 'Bookings' },
  { to: routes.members, label: 'Members' },
  { to: routes.classes, label: 'Classes' },
  // Staff only, and hidden rather than disabled for an instructor. A link that
  // leads to a 403 teaches somebody the tool is broken; one that is not there
  // teaches them nothing at all, which is correct — this is not their job. The
  // server refuses either way, which is the part that matters.
  { to: routes.people, label: 'People', staffOnly: true },
  { to: routes.reports, label: 'Reports' },
]

export function Rail() {
  const user = useCurrentUser()
  const signOut = useSignOut()
  const alerts = useAlertCount()

  return (
    <nav
      aria-label="Sections"
      className="flex w-[304px] shrink-0 flex-col justify-between px-7 py-10"
    >
      <div className="flex flex-col gap-12">
        <div>
          {/* The wordmark goes home, which on this product means out of the tool
              and back to the page that explains it. A logo returning somewhere is
              one of the few conventions on the web strong enough not to need an
              underline announcing it, so it gets a hover colour and nothing else
              — an underlined wordmark reads as a mistake.

              Only the name is the link. The role beneath it is a label, and
              swallowing it into the target would make the click area a strange
              two-line block with a different meaning on each line. */}
          <Link
            to={routes.landing}
            className="display inline-block whitespace-nowrap text-28 transition-colors duration-[120ms] hover:text-ink"
          >
            Mornington Studios
          </Link>
          <p className="tracked mt-1 text-11 text-graphite">
            {user.role === 'staff' ? 'Front desk' : 'Instructor'}
          </p>
        </div>

        <ul className="flex flex-col gap-1">
          {LINKS.filter((link) => !link.staffOnly || user.role === 'staff').map((link) => (
            <li key={link.to}>
              <NavLink
                to={link.to}
                end={link.to === routes.today}
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
                    {link.to === routes.members && (alerts.data?.count ?? 0) > 0 && (
                      <span className="text-11 font-medium text-wait-ink">{alerts.data?.count}</span>
                    )}
                  </>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex flex-col gap-4">
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
