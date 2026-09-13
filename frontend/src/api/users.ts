import { request } from './client'
import type { Teacher, User, UserCreate, UserUpdate, Uuid } from './types'

/**
 * The people who can sign in — as opposed to members, who cannot.
 *
 * Both calls are staff-only on the server. Reading the list feeds the instructor
 * pickers on goals 3, 5 and 7; writing to it is how somebody becomes available to
 * those pickers in the first place.
 */
export function listTeachers(): Promise<Teacher[]> {
  return request<Teacher[]>('/users')
}

export function createUser(body: UserCreate): Promise<User> {
  return request<User>('/users', { method: 'POST', body })
}

/** Set or clear what somebody is paid to lead one session. */
export function setSessionRate(id: Uuid, body: UserUpdate): Promise<Teacher> {
  return request<Teacher>(`/users/${id}`, { method: 'PATCH', body })
}
