import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createMember, getMember, listMembers, updateMember, type MemberQuery } from '@/api/members'
import { keys } from '@/lib/query-keys'
import type { MemberCreate, MemberUpdate, Uuid } from '@/api/types'

export function useMembers(query: MemberQuery, enabled = true) {
  return useQuery({
    queryKey: keys.members(query),
    queryFn: () => listMembers(query),
    enabled,
    placeholderData: (previous) => previous,
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
