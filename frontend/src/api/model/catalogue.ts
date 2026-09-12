// What the studio teaches, and the rooms it teaches in.

import type { Instant, Uuid } from './common'

// --- classes and rooms ------------------------------------------------------

export interface StudioClass {
  id: Uuid
  title: string
  description: string
  discipline: string
  default_duration_min: number
  default_capacity: number
  archived_at: Instant | null
  version: number
  created_at: Instant
  updated_at: Instant
}

export interface ClassCreate {
  title: string
  description?: string
  discipline: string
  default_duration_min: number
  default_capacity: number
}

/** `version` is not optional. It is what makes a stale edit form fail loudly. */
export type ClassUpdate = Partial<ClassCreate> & { version: number }

export interface Room {
  id: Uuid
  name: string
}
