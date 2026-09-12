import { request } from './client'
import type { Member, MemberCreate, MemberUpdate, Page, Uuid } from './types'

export interface MemberQuery {
  q?: string
  limit?: number
  offset?: number
}

/**
 * List and search members (goal 1).
 *
 * `q` matches name or email. The backend casts to text before the trigram
 * comparison — the email column is `citext`, and the planner will not use a
 * trigram index through the case-insensitive operator — so this is a real index
 * scan rather than the sequential one it looks like.
 */
export function listMembers(query: MemberQuery = {}): Promise<Page<Member>> {
  return request<Page<Member>>('/members', { query: { ...query } })
}

export function getMember(id: Uuid): Promise<Member> {
  return request<Member>(`/members/${id}`)
}

export function createMember(body: MemberCreate): Promise<Member> {
  return request<Member>('/members', { method: 'POST', body })
}

/** Changing `membership_expiry` also clears any dismissed alert, by trigger. */
export function updateMember(id: Uuid, body: MemberUpdate): Promise<Member> {
  return request<Member>(`/members/${id}`, { method: 'PATCH', body })
}
