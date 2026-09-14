import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  createMember,
  enableMemberLogin,
  getMember,
  listMembers,
  updateMember,
  type MemberQuery,
} from '@/api/members'
import { keys } from '@/lib/query-keys'
import type { MemberCreate, MemberUpdate, Uuid } from '@/api/types'

export function useMembers(query: MemberQuery, enabled = true) {
  return useQuery({
    queryKey: keys.members(query),
    queryFn: () => listMembers(query),
    enabled,
    // No `placeholderData`. Keeping the previous result on screen while the next
    // one loads reads as polish on a laptop, where the gap is 3ms and invisible.
    // Against a real database it is a lie: the controls say one thing and the
    // rows below them describe something else, for as long as the round trip
    // takes. The moment the query key changes, what is on screen is answering a
    // question nobody asked any more — so it goes, and the skeleton says so.
    //
    // The searches that feed these keys are debounced, so this costs one loading
    // state per settled search rather than one per keystroke.
  })
}

export function useMember(id: Uuid) {
  return useQuery({
    queryKey: keys.member(id),
    queryFn: () => getMember(id),
  })
}

export function useCreateMember() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: MemberCreate) => createMember(body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['members'] })
      void client.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

/**
 * Edit a member.
 *
 * Invalidates the alert feed as well as the member: changing an expiry date is
 * how a renewal is recorded, and the database clears any dismissed alert for the
 * old date at the same moment. Leaving the feed stale would show a member as
 * needing attention seconds after somebody fixed it.
 */
export function useUpdateMember() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, body }: { id: Uuid; body: MemberUpdate }) => updateMember(id, body),
    onSuccess: (member) => {
      void client.invalidateQueries({ queryKey: ['members'] })
      void client.invalidateQueries({ queryKey: keys.member(member.id) })
      void client.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}

/**
 * Switch on a member's login.
 *
 * Invalidates the member lists so the row stops offering a button that would now
 * be refused — the endpoint answers a second call with a 409 rather than quietly
 * resetting the password, so a stale row is a dead end rather than a surprise.
 *
 * Not the alerts feed, unlike the other two mutations here: a login has nothing
 * to do with when a membership expires, which is the entire point of the feature.
 */
export function useEnableMemberLogin() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, password }: { id: Uuid; password: string }) =>
      enableMemberLogin(id, password),
    onSuccess: (member) => {
      void client.invalidateQueries({ queryKey: ['members'] })
      void client.invalidateQueries({ queryKey: keys.member(member.id) })
    },
  })
}
