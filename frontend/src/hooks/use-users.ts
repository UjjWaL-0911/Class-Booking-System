import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { createUser, listTeachers } from '@/api/users'
import { keys } from '@/lib/query-keys'

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
