import { request } from './client'
import type { PublicSchedule } from './types'

/**
 * The timetable, for somebody who has not signed in.
 *
 * It goes through the same `request` helper as everything else — which attaches an
 * access token when there is one and does not when there is not. That is fine here
 * and worth being deliberate about: the endpoint ignores credentials entirely, so a
 * signed-in visitor and a stranger see exactly the same page. A second fetch path
 * that skipped the token would be a second thing to keep correct for no gain.
 */
export function getPublicSchedule(days?: number): Promise<PublicSchedule> {
  return request<PublicSchedule>('/public/schedule', {
    query: days === undefined ? {} : { days },
  })
}
