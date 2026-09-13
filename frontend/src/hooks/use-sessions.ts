import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  addCoInstructor,
  createSession,
  deleteSession,
  generateSessions,
  getSession,
  listSessions,
  removeCoInstructor,
  updateSession,
  type SessionQuery,
} from '@/api/sessions'
import { keys } from '@/lib/query-keys'
import type { RecurrenceCreate, SessionCreate, SessionUpdate, Uuid } from '@/api/types'

export function useSessions(query: SessionQuery, enabled = true) {
  return useQuery({
    queryKey: keys.sessions(query),
    queryFn: () => listSessions(query),
    enabled,
    placeholderData: (previous) => previous,
  })
}

export function useSession(id: Uuid) {
  return useQuery({
    queryKey: keys.session(id),
    queryFn: () => getSession(id),
  })
}

function useSessionWriteInvalidation() {
  const client = useQueryClient()
  return (id?: Uuid) => {
    void client.invalidateQueries({ queryKey: ['sessions'] })
    void client.invalidateQueries({ queryKey: keys.dashboard })
    if (id) void client.invalidateQueries({ queryKey: keys.session(id) })
  }
}

export function useCreateSession() {
  const invalidate = useSessionWriteInvalidation()
  return useMutation({
    mutationFn: (body: SessionCreate) => createSession(body),
    onSuccess: (session) => invalidate(session.id),
  })
}

/**
 * Edit a session.
 *
 * Also invalidates bookings, for the same reason delete does: raising capacity
 * fills the new seats from the waitlist in the same transaction, so a roster or a
 * bookings list open beside this dialog is now describing rows that have moved.
 */
export function useUpdateSession() {
  const client = useQueryClient()
  const invalidate = useSessionWriteInvalidation()
  return useMutation({
    mutationFn: ({ id, body }: { id: Uuid; body: SessionUpdate }) => updateSession(id, body),
    onSuccess: (session) => {
      invalidate(session.id)
      void client.invalidateQueries({ queryKey: ['bookings'] })
    },
  })
}

/**
 * Delete a session.
 *
 * Also invalidates bookings: the delete cancels whatever active bookings remain,
 * so any list showing them is now describing rows that have changed status.
 */
export function useDeleteSession() {
  const client = useQueryClient()
  const invalidate = useSessionWriteInvalidation()
  return useMutation({
    mutationFn: (id: Uuid) => deleteSession(id),
    onSuccess: () => {
      invalidate()
      void client.invalidateQueries({ queryKey: ['bookings'] })
    },
  })
}

export function useAddCoInstructor() {
  const invalidate = useSessionWriteInvalidation()
  return useMutation({
    mutationFn: ({ sessionId, userId }: { sessionId: Uuid; userId: Uuid }) =>
      addCoInstructor(sessionId, userId),
    onSuccess: (session) => invalidate(session.id),
  })
}

export function useRemoveCoInstructor() {
  const invalidate = useSessionWriteInvalidation()
  return useMutation({
    mutationFn: ({ sessionId, userId }: { sessionId: Uuid; userId: Uuid }) =>
      removeCoInstructor(sessionId, userId),
    onSuccess: (session) => invalidate(session.id),
  })
}

/** Goal 7. The report is the point: the caller must show what was skipped. */
export function useGenerateSessions() {
  const invalidate = useSessionWriteInvalidation()
  return useMutation({
    mutationFn: (body: RecurrenceCreate) => generateSessions(body),
    onSuccess: () => invalidate(),
  })
}
