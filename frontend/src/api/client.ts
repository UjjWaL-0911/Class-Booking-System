/**
 * The one place this app talks to the network.
 *
 * Two things here are worth reading before changing anything.
 *
 * **The URL is always relative.** Never `http://localhost:8000`. The refresh
 * cookie is scoped to `/api/v1/auth` and `/auth/refresh` rejects a request whose
 * `Origin` it cannot verify, so a second origin means the cookie silently never
 * arrives. Development proxies `/api` through Vite; production rewrites it at the
 * static host. Same shape in both.
 *
 * **Refresh is single-flight.** Open the app on the Today screen and five queries
 * start at once. If each of them noticed the expired token and rotated
 * independently, four would present a refresh token that a sibling had already
 * consumed — and the backend treats a reused refresh token as theft and revokes
 * the whole family. The fix is not retry logic; it is making sure only one
 * rotation is ever in the air.
 */

import { ApiError, networkError, toApiError } from './errors'
import { clearSession, getAccessToken, needsRefresh, setSession } from './token-store'
import type { TokenResponse } from './types'

const BASE = '/api/v1'

/** A non-simple header, which is what forces the preflight that stops a foreign
 *  origin calling refresh with the ambient cookie. The backend requires it. */
const CSRF_HEADER = 'x-refresh-request'

export type QueryValue = string | number | boolean | null | undefined
export type Query = Record<string, QueryValue | QueryValue[]>

function buildUrl(path: string, query?: Query): string {
  if (!query) return `${BASE}${path}`
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query)) {
    const values = Array.isArray(value) ? value : [value]
    for (const item of values) {
      // Omit rather than send an empty string: `?q=` and no `q` at all mean
      // different things to a search endpoint.
      if (item === null || item === undefined || item === '') continue
      params.append(key, String(item))
    }
  }
  const qs = params.toString()
  return qs ? `${BASE}${path}?${qs}` : `${BASE}${path}`
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PATCH' | 'DELETE'
  body?: unknown
  query?: Query
  signal?: AbortSignal
  /** Set on the auth endpoints themselves, which must not try to refresh. */
  skipAuth?: boolean
}

let inFlightRefresh: Promise<boolean> | null = null

async function rotate(): Promise<boolean> {
  let response: Response
  try {
    response = await fetch(`${BASE}/auth/refresh`, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { [CSRF_HEADER]: '1' },
    })
  } catch {
    // A network failure is not a sign-out. The cookie is probably still good and
    // the next attempt may well work, so leave the session alone.
    return false
  }

  if (!response.ok) {
    clearSession()
    return false
  }

  const token = (await response.json()) as TokenResponse
  setSession(token.access_token, token.expires_at, token.user)
  return true
}

/** Rotate the session, collapsing concurrent callers onto one request. */
export function refreshSession(): Promise<boolean> {
  inFlightRefresh ??= rotate().finally(() => {
    inFlightRefresh = null
  })
  return inFlightRefresh
}

/**
 * Restore a session on page load.
 *
 * The access token did not survive the reload, but the refresh cookie did. This
 * is what turns that cookie into a signed-in user, and the only thing standing
 * between a refresh of the page and the login form.
 */
export async function restoreSession(): Promise<boolean> {
  const restored = await refreshSession()
  if (!restored) clearSession()
  return restored
}

async function send(path: string, options: RequestOptions, token: string | null): Promise<Response> {
  const headers: Record<string, string> = {}
  if (token !== null) headers['authorization'] = `Bearer ${token}`
  if (options.body !== undefined) headers['content-type'] = 'application/json'

  try {
    return await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      credentials: 'same-origin',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (cause) {
    // An aborted request is the app cancelling itself — a navigation, a stale
    // query — not a failure to report.
    if (cause instanceof DOMException && cause.name === 'AbortError') throw cause
    throw networkError(cause)
  }
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  if (!options.skipAuth && needsRefresh()) {
    await refreshSession()
  }

  let response = await send(path, options, options.skipAuth ? null : getAccessToken())

  // One retry, and only for a 401. A token can expire between the check above and
  // the server reading it, and a clock a few seconds out is enough to do it. A
  // second 401 after a successful rotation means the answer really is no.
  if (response.status === 401 && !options.skipAuth) {
    const rotated = await refreshSession()
    if (rotated) {
      response = await send(path, options, getAccessToken())
    } else {
      clearSession()
    }
  }

  if (!response.ok) throw await toApiError(response)
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

/**
 * Fetch a file and hand it to the browser (goal 7's CSV).
 *
 * A plain link cannot do this: the endpoint needs an `Authorization` header, and
 * an anchor sends none. So the bytes come through the same authenticated path as
 * everything else and the download is triggered from the blob.
 */
export async function downloadFile(path: string, fallbackName: string): Promise<void> {
  if (needsRefresh()) await refreshSession()

  const response = await send(path, {}, getAccessToken())
  if (!response.ok) throw await toApiError(response)

  const disposition = response.headers.get('content-disposition') ?? ''
  const match = /filename="?([^";]+)"?/.exec(disposition)
  const filename = match?.[1] ?? fallbackName

  const url = URL.createObjectURL(await response.blob())
  try {
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.append(anchor)
    anchor.click()
    anchor.remove()
  } finally {
    // Revoked on the next tick rather than immediately: Safari has not finished
    // reading the blob when click() returns.
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
}

export { ApiError }
