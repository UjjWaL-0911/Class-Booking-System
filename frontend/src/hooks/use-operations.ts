import { useQuery } from '@tanstack/react-query'
import { getOperations } from '@/api/insights'
import { keys } from '@/lib/query-keys'

/**
 * Room utilisation and instructor pay over one window.
 *
 * Ten minutes of staleness, unlike the twenty seconds everything operational uses.
 * These are questions about a month that has already happened — the answer does
 * not move while somebody is reading it, and refetching it every time a tab
 * regains focus would spend a free-tier instance's budget on a number that has not
 * changed since last Tuesday.
 */
export function useOperations(from: string, to: string) {
  return useQuery({
    queryKey: keys.operations(from, to),
    queryFn: () => getOperations({ date_from: from, date_to: to }),
    staleTime: 600_000,
  })
}
