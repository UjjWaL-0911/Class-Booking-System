import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  archiveClass,
  createClass,
  createRoom,
  listClasses,
  listRooms,
  restoreClass,
  updateClass,
} from '@/api/classes'
import { keys } from '@/lib/query-keys'
import type { ClassCreate, ClassUpdate, Uuid } from '@/api/types'

export function useClasses(includeArchived = false) {
  return useQuery({
    queryKey: keys.classes(includeArchived),
    queryFn: () => listClasses(includeArchived),
  })
}

export function useRooms() {
  return useQuery({
    queryKey: keys.rooms,
    queryFn: listRooms,
    staleTime: 600_000,
  })
}

function useClassWriteInvalidation() {
  const client = useQueryClient()
  return () => {
    void client.invalidateQueries({ queryKey: ['classes'] })
    // Sessions carry the class title and discipline, so a renamed class changes
    // every row of the timetable.
    void client.invalidateQueries({ queryKey: ['sessions'] })
  }
}

export function useCreateClass() {
  const invalidate = useClassWriteInvalidation()
  return useMutation({
    mutationFn: (body: ClassCreate) => createClass(body),
    onSuccess: invalidate,
  })
}

export function useUpdateClass() {
  const invalidate = useClassWriteInvalidation()
  return useMutation({
    mutationFn: ({ id, body }: { id: Uuid; body: ClassUpdate }) => updateClass(id, body),
    onSuccess: invalidate,
  })
}

/** Goal 2: hides the class, keeps its sessions and bookings. */
export function useArchiveClass() {
  const invalidate = useClassWriteInvalidation()
  return useMutation({
    mutationFn: (id: Uuid) => archiveClass(id),
    onSuccess: invalidate,
  })
}

export function useRestoreClass() {
  const invalidate = useClassWriteInvalidation()
  return useMutation({
    mutationFn: (id: Uuid) => restoreClass(id),
    onSuccess: invalidate,
  })
}

export function useCreateRoom() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => createRoom(name),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.rooms })
    },
  })
}
