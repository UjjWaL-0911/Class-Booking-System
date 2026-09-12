/**
 * Which colour scheme the interface is in, and who decided.
 *
 * Two values, kept apart on purpose:
 *
 *   **preference** — what the person chose: `auto`, `light` or `dark`. Stored.
 *   **resolved**   — what is actually on screen: `light` or `dark`. Derived.
 *
 * Only the resolved value reaches the DOM, as `data-theme` on `<html>`. That is
 * what lets the stylesheet carry exactly one dark block: "follow the system" is
 * settled here, in a `matchMedia` listener, rather than duplicated into a
 * `prefers-color-scheme` media query that would have to repeat every token.
 *
 * `auto` is the default because a studio laptop that goes dark at dusk should
 * take this app with it without anybody being asked.
 */

export type ThemePreference = 'auto' | 'light' | 'dark'
export type ResolvedTheme = 'light' | 'dark'

const STORAGE_KEY = 'mornington.theme'

const DARK_QUERY = '(prefers-color-scheme: dark)'

/**
 * Read the stored choice.
 *
 * Wrapped, because `localStorage` is not merely empty in a private window or
 * with site data blocked — the accessor itself throws. A colour scheme is not
 * worth a blank screen.
 */
export function readPreference(): ThemePreference {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'light' || stored === 'dark' || stored === 'auto') return stored
  } catch {
    // Fall through to the default.
  }
  return 'auto'
}

export function writePreference(preference: ThemePreference): void {
  try {
    localStorage.setItem(STORAGE_KEY, preference)
  } catch {
    // The choice still applies for this page; it just will not be remembered.
  }
}

export function systemTheme(): ResolvedTheme {
  return typeof matchMedia === 'function' && matchMedia(DARK_QUERY).matches ? 'dark' : 'light'
}

export function resolve(preference: ThemePreference): ResolvedTheme {
  return preference === 'auto' ? systemTheme() : preference
}

/** Put the resolved scheme where the stylesheet can see it. */
export function apply(theme: ResolvedTheme): void {
  document.documentElement.dataset['theme'] = theme
}

/**
 * Call `listener` whenever the operating system's scheme changes.
 *
 * Only matters while the preference is `auto`; the store decides that, so this
 * function stays a plain subscription with no opinion of its own.
 */
export function watchSystem(listener: () => void): () => void {
  if (typeof matchMedia !== 'function') return () => {}
  const query = matchMedia(DARK_QUERY)
  query.addEventListener('change', listener)
  return () => query.removeEventListener('change', listener)
}
