import { request } from './client'
import type { User, UserCreate } from './types'

/**
 * The people who can sign in — as opposed to members, who cannot.
 *
 * Both calls are staff-only on the server. Reading the list feeds the instructor
 * pickers on goals 3, 5 and 7; writing to it is how somebody becomes available to
 * those pickers in the first place.
 */
export function listTeachers(): Promise<User[]> {
  return request<User[]>('/users')
}

export function createUser(body: UserCreate): Promise<User> {
  return request<User>('/users', { method: 'POST', body })
}
