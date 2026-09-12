/**
 * Where the access token lives: in a module variable, and nowhere else.
 *
 * Not `localStorage`, not `sessionStorage`, not a cookie this script can read. The
 * backend deliberately withholds the refresh token from JavaScript — it travels
 * only as an httpOnly cookie — and storing the access token somewhere readable
 * would hand most of that protection back. An XSS bug can still use the token
 * while the page is open; it cannot walk away with a credential that outlives the
 * tab.
 *
 * The cost is that a page reload starts with nothing, which is why the app asks
 * for a rotation on boot (see `restoreSession`). That request is the only reason
 * a refresh cookie exists.
 */

import type { User } from './types'

export type SessionStatus = 'unknown' | 'signed-in' | 'signed-out'

export interface SessionState {
  status: SessionStatus
  user: User | null
  accessToken: string | null
  /** Epoch milliseconds. 0 when there is no token. */
  expiresAt: number
}

const SIGNED_OUT: SessionState = {
  status: 'signed-out',
  user: null,
  accessToken: null,
  expiresAt: 0,
}

// `unknown` rather than `signed-out` on first load: the difference is whether to
// show the sign-in page or wait, and getting it wrong makes every reload flash
// the login form at somebody who is already signed in.
let state: SessionState = { ...SIGNED_OUT, status: 'unknown' }

const listeners = new Set<() => void>()

function emit(next: SessionState): void {
  state = next
  for (const listener of listeners) listener()
}

export function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Stable between changes, which is what `useSyncExternalStore` requires. */
export function getSessionState(): SessionState {
  return state
}

export function setSession(accessToken: string, expiresAt: string, user: User): void {
  emit({
    status: 'signed-in',
    user,
    accessToken,
    expiresAt: new Date(expiresAt).getTime(),
  })
}

export function clearSession(): void {
  emit({ ...SIGNED_OUT })
}

export function getAccessToken(): string | null {
  return state.accessToken
}

/**
 * True when the token is gone or close enough to expiry that using it would
 * probably earn a 401.
 *
 * The margin is a whole minute against a fifteen-minute token: refreshing early
 * costs one cheap request, while refreshing late costs a failed request, a
 * refresh, and a retry — and does it on the user's click rather than before it.
 */
const EXPIRY_MARGIN_MS = 60_000

export function needsRefresh(): boolean {
  if (state.accessToken === null) return true
  return state.expiresAt - Date.now() < EXPIRY_MARGIN_MS
}
