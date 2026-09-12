import { useSyncExternalStore } from 'react'
import {
  apply,
  readPreference,
  resolve,
  watchSystem,
  writePreference,
  type ResolvedTheme,
  type ThemePreference,
} from '@/lib/theme'

/**
 * The colour scheme, as a store rather than a context.
 *
 * Same reason as the access token: it is written from outside React. The
 * operating system can change the scheme while nothing is rendering, and the
 * `data-theme` attribute has to follow. `useSyncExternalStore` makes the DOM the
 * source of truth and React the subscriber, which is the right way round —
 * mirroring it into component state would mean two copies that can disagree.
 */
interface ThemeState {
  preference: ThemePreference
  resolved: ResolvedTheme
}

let state: ThemeState = (() => {
  const preference = readPreference()
  return { preference, resolved: resolve(preference) }
})()

const listeners = new Set<() => void>()

function emit(next: ThemeState): void {
  state = next
  apply(next.resolved)
  for (const listener of listeners) listener()
}

// The system can change under us. Re-resolving is only a change when the
// preference is `auto`; an explicit choice ignores it.
watchSystem(() => {
  if (state.preference !== 'auto') return
  const resolved = resolve('auto')
  if (resolved !== state.resolved) emit({ ...state, resolved })
})

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** Stable between changes, which is what `useSyncExternalStore` requires. */
function getSnapshot(): ThemeState {
  return state
}

export function useTheme(): ThemeState & { setPreference: (next: ThemePreference) => void } {
  const current = useSyncExternalStore(subscribe, getSnapshot)
  return { ...current, setPreference }
}

export function setPreference(preference: ThemePreference): void {
  writePreference(preference)
  emit({ preference, resolved: resolve(preference) })
}
