import { Outlet } from 'react-router-dom'
import { MemberRail } from './member-rail'
import { Page } from './app-shell'

/**
 * The member's side of the building, laid out like the studio's.
 *
 * A separate shell from `AppShell` rather than the same one with items hidden,
 * and the reason is structural: `AppShell` mounts `StudioProvider`, which fetches
 * the dashboard to establish the studio's timezone — an endpoint a member is
 * refused. Reusing it would be a shell whose first act is a 403.
 *
 * It needs no timezone of its own. Every date, time and "has this passed" arrives
 * from the server already converted and already decided, so there is no date
 * arithmetic anywhere on this side — the right answer for screens that will
 * mostly be read on a phone in some other timezone.
 *
 * The *frame* is shared, though: same rail geometry, same page padding, same
 * ground. One product, and somebody who is both a customer and a colleague should
 * not have to learn two interfaces.
 */
export function MemberShell() {
  return (
    <div className="flex min-h-screen bg-paper">
      <MemberRail />
      <main className="min-w-0 flex-1">
        <Page>
          <Outlet />
        </Page>
      </main>
    </div>
  )
}
