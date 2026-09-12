import { createContext, useContext } from 'react'
import type { Dashboard, LocalDate } from '@/api/types'

/**
 * The studio's own timezone and its own idea of today.
 *
 * Both come from the server, and neither is negotiable on the client. The studio
 * has one timezone, set in its configuration; `Intl.DateTimeFormat().resolvedOptions()`
 * gives the *viewer's*, which is a different thing and is wrong for a manager
 * checking the desk from abroad. Four of the ten goals produce different numbers
 * under a different timezone, so this is the value the whole interface formats
 * against.
 */
export interface Studio {
  timeZone: string
  /** The studio's today, which is not always the viewer's. */
  today: LocalDate
  dashboard: Dashboard
}

export const StudioContext = createContext<Studio | null>(null)

export function useStudio(): Studio {
  const value = useContext(StudioContext)
  if (value === null) {
    throw new Error('useStudio was called outside StudioProvider.')
  }
  return value
}
