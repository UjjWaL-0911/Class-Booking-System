import { useEffect, useRef, useState } from 'react'

/**
 * Reveal a section the first time it is scrolled into view.
 *
 * `IntersectionObserver` rather than a scroll handler, because a scroll handler
 * runs on every frame of every scroll for the whole life of the page to answer a
 * question that matters once.
 *
 * It disconnects after firing. A section that fades back out when you scroll past
 * and in again when you return is a section that never settles, and the second
 * viewing is not an arrival.
 *
 * The default is **visible**. If the observer is missing, or the callback never
 * runs, the content is simply there — an animation failing should never be able
 * to hide a page.
 */
export function useOnView<T extends HTMLElement>(): {
  ref: React.RefObject<T | null>
  shown: boolean
} {
  const ref = useRef<T>(null)
  const [shown, setShown] = useState(() => typeof IntersectionObserver !== 'function')

  useEffect(() => {
    const element = ref.current
    if (element === null || typeof IntersectionObserver !== 'function') {
      setShown(true)
      return
    }

    const observer = new IntersectionObserver(
      (entries) => {
        // A little of the section is enough. Waiting for half of a tall block
        // means it arrives long after somebody has started reading it.
        if (entries.some((entry) => entry.isIntersecting)) {
          setShown(true)
          observer.disconnect()
        }
      },
      { rootMargin: '0px 0px -12% 0px' },
    )

    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  return { ref, shown }
}
