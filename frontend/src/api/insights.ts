import { request } from './client'
import type { AlertFeed, Dashboard, Uuid } from './types'

/**
 * Goal 8's numbers, in one request.
 *
 * Scoped to the viewer: an instructor's figures describe their own teaching
 * rather than the whole studio. `timezone` and `as_of` come back with the
 * numbers, which is what lets the interface state whose "today" it is showing
 * instead of assuming the browser's.
 */
export function getDashboard(): Promise<Dashboard> {
  return request<Dashboard>('/dashboard')
}

/** Goal 10. Includes the already-expired, with `days_remaining` negative. */
export function getMembershipAlerts(): Promise<AlertFeed> {
  return request<AlertFeed>('/alerts/memberships')
}

/**
 * Just the number, for the rail badge.
 *
 * A separate endpoint because the badge is on every screen while the feed itself
 * is opened rarely, and sending twenty rows to render one digit is the expensive
 * way round.
 */
export function getAlertCount(): Promise<{ count: number }> {
  return request<{ count: number }>('/alerts/memberships/count')
}

/**
 * Dismiss one member's alert.
 *
 * Scoped to the expiry date it was dismissed *for*: change the date and the alert
 * comes back, which is the behaviour you want when somebody renews and then
 * lapses again rather than a permanent mute.
 */
export function dismissMembershipAlert(memberId: Uuid): Promise<void> {
  return request<void>(`/alerts/memberships/${memberId}/dismiss`, { method: 'POST' })
}
