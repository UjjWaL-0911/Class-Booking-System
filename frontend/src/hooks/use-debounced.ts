import { useEffect, useState } from 'react'

/**
 * Hold a value still until the typing stops.
 *
 * 250ms, which is roughly the gap between words rather than between keystrokes.
 * The search endpoints behind this run a trigram match over a single studio's
 * members and bookings — they are not slow — but a request per character on a
 * free-tier instance spends the request budget on prefixes nobody wanted results
 * for.
 */
export function useDebounced<T>(value: T, delayMs = 250): T {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return settled
}
