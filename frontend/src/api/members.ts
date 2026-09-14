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

/**
 * Let one member sign in and book for themselves.
 *
 * Staff only, and there is no public equivalent — a member account implies a
 * membership, a membership implies somebody paid, and an endpoint on the open
 * internet cannot know that. See `schemas/member.py` for the whole argument.
 *
 * It grants an account, never a membership: `membership_expiry` is untouched, so
 * whether this person may book is still decided by the rule that already decided
 * it. Enabling a login for a lapsed member gives them a working sign-in and a
 * refusal at the point of booking, which is the correct behaviour rather than an
 * edge case.
 */
export function enableMemberLogin(id: Uuid, password: string): Promise<Member> {
  return request<Member>(`/members/${id}/account`, { method: 'POST', body: { password } })
}
