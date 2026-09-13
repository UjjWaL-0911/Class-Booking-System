import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createUser, listTeachers, setSessionRate } from '@/api/users'
import { keys, rateWriteAffects } from '@/lib/query-keys'
import type { Uuid } from '@/api/types'

/** Everyone who can lead a class — active accounts of either role. */
export function useTeachers() {
  return useQuery({
    queryKey: keys.teachers,
    queryFn: listTeachers,
    // A studio's staff list changes when somebody is hired. Ten minutes.
    staleTime: 600_000,
  })
}

/**
 * Add a colleague.
 *
 * Invalidating `teachers` is the whole point rather than housekeeping: a new
 * instructor has to appear in the pickers on the scheduling dialogs immediately,
 * and those read this exact key. Without it the person who just added somebody
 * would be told to wait ten minutes before they could put them in front of a
 * class.
 */
export function useCreateUser() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: createUser,
    onSuccess: () => void client.invalidateQueries({ queryKey: keys.teachers }),
  })
}

/** Set or clear somebody's session rate. `null` clears it, which is not zero. */
export function useSetRate() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: ({ id, minor }: { id: Uuid; minor: number | null }) =>
      setSessionRate(id, { session_rate_minor: minor }),
    onSuccess: () => {
      for (const key of rateWriteAffects) {
        void client.invalidateQueries({ queryKey: key })
      }
    },
  })
}
