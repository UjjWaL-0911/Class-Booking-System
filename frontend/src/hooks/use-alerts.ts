import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { dismissMembershipAlert, getAlertCount, getMembershipAlerts } from '@/api/insights'
import { keys } from '@/lib/query-keys'
import { useIsStaff } from './use-auth'
import type { Uuid } from '@/api/types'

/**
 * Goal 10's feed. Staff only, which is enforced on the server — this `enabled`
 * flag exists so an instructor's screen does not fire a request it knows will
 * come back 403, not as the access control itself.
 */
export function useMembershipAlerts() {
  const isStaff = useIsStaff()
  return useQuery({
    queryKey: keys.alerts,
    queryFn: getMembershipAlerts,
    enabled: isStaff,
  })
}

export function useAlertCount() {
  const isStaff = useIsStaff()
  return useQuery({
    queryKey: keys.alertCount,
    queryFn: getAlertCount,
    enabled: isStaff,
    // The badge is on every screen. A minute is often enough for a number that
    // changes when somebody renews a membership, and rare enough not to spend a
    // free-tier instance's budget on a digit.
    staleTime: 60_000,
  })
}

export function useDismissAlert() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (memberId: Uuid) => dismissMembershipAlert(memberId),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: ['alerts'] })
    },
  })
}
