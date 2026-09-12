import { request } from './client'
import { clearSession, setSession } from './token-store'
import type { TokenResponse, User } from './types'

/**
 * Sign in (goal 1).
 *
 * `skipAuth` matters: without it the client would try to rotate a session that
 * does not exist yet before every login attempt, and a failed rotation clears the
 * store — so a wrong password would log out whoever was already signed in.
 */
export async function signIn(email: string, password: string): Promise<User> {
  const token = await request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: { email, password },
    skipAuth: true,
  })
  setSession(token.access_token, token.expires_at, token.user)
  return token.user
}

/**
 * Sign out.
 *
 * The local state is cleared whatever the server says. A network failure here
 * must not leave somebody looking at a signed-in interface they have asked to
 * leave; the server-side revocation is the part that can safely be retried, and
 * the cookie expires on its own regardless.
 */
export async function signOut(): Promise<void> {
  try {
    await request<void>('/auth/logout', { method: 'POST' })
  } finally {
    clearSession()
  }
}

export function fetchMe(): Promise<User> {
  return request<User>('/auth/me')
}
