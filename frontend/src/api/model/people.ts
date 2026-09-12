// Accounts that sign in, and the member records they book on behalf of.

import type { Instant, LocalDate, UserRole, Uuid } from './common'

// --- auth -------------------------------------------------------------------

/** Staff add colleagues; there is no public registration. See users.py. */
export interface UserCreate {
  email: string
  full_name: string
  role: UserRole
  password: string
}

export interface User {
  id: Uuid
  email: string
  full_name: string
  role: UserRole
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
