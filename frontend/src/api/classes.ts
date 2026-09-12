import { request } from './client'
import type { ClassCreate, ClassUpdate, Room, StudioClass, Uuid } from './types'

/** Goal 2. Archived classes are excluded unless asked for. */
export function listClasses(includeArchived = false): Promise<StudioClass[]> {
  return request<StudioClass[]>('/classes', {
    query: { include_archived: includeArchived },
  })
}

export function getClass(id: Uuid): Promise<StudioClass> {
  return request<StudioClass>(`/classes/${id}`)
}

export function createClass(body: ClassCreate): Promise<StudioClass> {
  return request<StudioClass>('/classes', { method: 'POST', body })
}

/**
 * Edit a class.
 *
 * `version` is mandatory. Two people with the edit form open is not a rare case
 * at a front desk with one shared screen and one manager's laptop, and without
 * the version the second save silently discards the first.
 */
export function updateClass(id: Uuid, body: ClassUpdate): Promise<StudioClass> {
  return request<StudioClass>(`/classes/${id}`, { method: 'PATCH', body })
}

/**
 * Archive, not delete: goal 2 keeps the sessions and bookings of a class that is
 * no longer taught.
 *
 * No `version` here, unlike `updateClass`. Archiving is idempotent — twice is the
 * same as once — so there is nothing for a stale version to protect against, and
 * demanding one would only make the button fail after somebody else edited the
 * description.
 */
export function archiveClass(id: Uuid): Promise<StudioClass> {
  return request<StudioClass>(`/classes/${id}/archive`, { method: 'POST' })
}

export function restoreClass(id: Uuid): Promise<StudioClass> {
  return request<StudioClass>(`/classes/${id}/restore`, { method: 'POST' })
}

export function listRooms(): Promise<Room[]> {
  return request<Room[]>('/rooms')
}

export function createRoom(name: string): Promise<Room> {
  return request<Room>('/rooms', { method: 'POST', body: { name } })
}
