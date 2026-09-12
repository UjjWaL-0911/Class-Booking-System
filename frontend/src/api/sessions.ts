import { request } from './client'
import type {
  GenerationReport,
  LocalDate,
  Page,
  RecurrenceCreate,
  Session,
  SessionCreate,
  SessionUpdate,
  User,
  Uuid,
} from './types'

export interface SessionQuery {
  class_id?: Uuid
  date_from?: LocalDate
  date_to?: LocalDate
  include_archived_classes?: boolean
  limit?: number
  offset?: number
}

/**
 * List sessions (goals 3 and 5).
 *
 * For an instructor this endpoint *is* goal 5's "one list of every session where
 * they are the primary instructor or a co-instructor" — the server's visibility
 * filter produces it, so the interface does not ask for it and cannot get it
 * wrong. Staff see the whole studio from the same call.
 */
export function listSessions(query: SessionQuery = {}): Promise<Page<Session>> {
  return request<Page<Session>>('/sessions', { query: { ...query } })
}

export function getSession(id: Uuid): Promise<Session> {
  return request<Session>(`/sessions/${id}`)
}

export function createSession(body: SessionCreate): Promise<Session> {
  return request<Session>('/sessions', { method: 'POST', body })
}

export function updateSession(id: Uuid, body: SessionUpdate): Promise<Session> {
  return request<Session>(`/sessions/${id}`, { method: 'PATCH', body })
}

/**
 * Delete a session.
 *
 * A soft delete that cancels whatever active bookings remain, each with its own
 * system-marked audit entry. Worth saying plainly in the confirmation dialog: the
 * members on this roster lose their places, and the timeline will tell them why.
 */
export function deleteSession(id: Uuid): Promise<void> {
  return request<void>(`/sessions/${id}`, { method: 'DELETE' })
}

/** Goal 5. Staff only, and no overlap check — only the primary is exclusive. */
export function addCoInstructor(sessionId: Uuid, userId: Uuid): Promise<Session> {
  return request<Session>(`/sessions/${sessionId}/co-instructors`, {
    method: 'POST',
    body: { user_id: userId },
  })
}

export function removeCoInstructor(sessionId: Uuid, userId: Uuid): Promise<Session> {
  return request<Session>(`/sessions/${sessionId}/co-instructors/${userId}`, {
    method: 'DELETE',
  })
}

/**
 * Generate a weekly schedule (goal 7).
 *
 * Returns a report, not a list: the interesting half of the response is what was
 * *skipped* and why, and the interface has to show both. `weekdays` follows
 * Python's convention, Monday is 0.
 */
export function generateSessions(body: RecurrenceCreate): Promise<GenerationReport> {
  return request<GenerationReport>('/sessions/generate', { method: 'POST', body })
}

/** Everyone who can be put in front of a class — active accounts, either role. */
export function listTeachers(): Promise<User[]> {
  return request<User[]>('/users')
}
