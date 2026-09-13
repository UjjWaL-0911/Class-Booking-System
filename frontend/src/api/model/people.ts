// Accounts that sign in, and the member records they book on behalf of.

import type { Instant, LocalDate, UserRole, Uuid } from './common'

// --- auth -------------------------------------------------------------------

/** Staff add colleagues; there is no public registration. See users.py. */
export interface UserCreate {
  email: string
  full_name: string
  role: UserRole
  password: string
  /** Minor units. Optional — an account may exist before a rate is agreed. */
  session_rate_minor?: number | null
}

export interface User {
  id: Uuid
  email: string
  full_name: string
  role: UserRole
}

/**
 * A colleague as the staff-only list returns them: a `User` plus their rate.
 *
 * Separate from `User` for the reason the server separates them — `User` is what
 * sign-in returns, and a pay rate has no business riding along on every login.
 * `null` is "no rate agreed", which is not zero.
 */
export interface Teacher extends User {
  session_rate_minor: number | null
}

/** The only editable thing about an account. `null` clears the rate. */
export interface UserUpdate {
  session_rate_minor: number | null
}

export interface TokenResponse {
  access_token: string
  token_type: string
  expires_at: Instant
  user: User
}
// --- members ----------------------------------------------------------------

export interface Member {
  id: Uuid
  full_name: string
  email: string
  membership_expiry: LocalDate
  notes: string
  created_at: Instant
  updated_at: Instant
}

export interface MemberCreate {
  full_name: string
  email: string
  membership_expiry: LocalDate
  notes?: string
}

export type MemberUpdate = Partial<MemberCreate>
