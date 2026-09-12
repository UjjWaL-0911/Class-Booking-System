import { useEffect, useRef, useState, type RefObject } from 'react'

/**
 * The name arrives filling the screen, then shrinks into its place in the nav.
 *
 * The technique matters, because the obvious version looks broken. Scaling a
 * 21px wordmark *up* by eight makes the browser rasterise it at 21px and stretch
 * the bitmap, so the letters arrive soft and sharpen as they shrink. So this runs
 * the other way round: a separate overlay is rendered at the large size, where it
 * is crisp, and scaled *down* onto the real wordmark's position. Downsampling has
 * no such artefact.
 *
 * Both ends are measured rather than guessed — the overlay's own box and the box
 * of the wordmark it is flying to. A hardcoded destination would be right at one
 * window size and visibly wrong at every other, and the mismatch shows as a jump
 * at the exact moment the two swap over.
 *
 * `prefers-reduced-motion` skips the whole thing: `onDone` fires immediately and
 * the page is simply there.
 */
const HOLD_MS = 380
const TRAVEL_MS = 760
const EASE = 'cubic-bezier(0.62, 0.04, 0.28, 1)'

export function StudioIntro({
  targetRef,
  children,
  onDone,
}: {
  /** The wordmark in the nav that this flies into. Must be laid out already. */
  targetRef: RefObject<HTMLElement | null>
  children: string
  onDone: () => void
}) {
  const overlayRef = useRef<HTMLSpanElement>(null)
  const [gone, setGone] = useState(false)

  useEffect(() => {
    const reduced =
      typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

    if (reduced) {
      setGone(true)
      onDone()
      return
    }

    let hold: number | undefined
    let reveal: number | undefined
    let clear: number | undefined
    let cancelled = false

    // Both boxes are measured, and the display face loads asynchronously with
    // `font-display: swap` — so measuring on mount measures the *fallback*
    // metrics. The scale would be computed from Georgia and applied to Instrument
    // Serif, and the name would land a few percent off its target. Waiting for
    // the font is the difference between landing on the wordmark and landing
    // near it.
    const ready = document.fonts?.ready ?? Promise.resolve()

    void ready.then(() => {
      if (cancelled) return

      const overlay = overlayRef.current
      const target = targetRef.current
      if (overlay === null || target === null) {
        setGone(true)
        onDone()
        return
      }

      start(overlay, target)
    })

    function start(overlay: HTMLSpanElement, target: HTMLElement) {
      const from = overlay.getBoundingClientRect()
      const to = target.getBoundingClientRect()

      // Guard the divide. A zero-width box means the element is not laid out and
      // the measurement is worthless; better to skip the flourish than to fling
      // the name somewhere arbitrary.
      if (from.width === 0 || to.width === 0) {
        setGone(true)
        onDone()
        return
      }

      const scale = to.width / from.width
      const dx = to.left + to.width / 2 - (from.left + from.width / 2)
      const dy = to.top + to.height / 2 - (from.top + from.height / 2)

      hold = window.setTimeout(() => {
        overlay.style.transition = `transform ${TRAVEL_MS}ms ${EASE}, opacity 240ms linear ${TRAVEL_MS - 200}ms`
        overlay.style.transform = `translate(${dx}px, ${dy}px) scale(${scale})`
        overlay.style.opacity = '0'
      }, HOLD_MS)

      // The content is revealed slightly before the name lands, so the page is
      // already coming up as it settles rather than waiting for it politely.
      reveal = window.setTimeout(onDone, HOLD_MS + TRAVEL_MS - 260)

      // Unmounted once it has finished rather than left at zero opacity: an
      // invisible element still holds a compositor layer for as long as
      // `will-change` is on it.
      clear = window.setTimeout(() => setGone(true), HOLD_MS + TRAVEL_MS + 80)
    }

    return () => {
      cancelled = true
      if (hold !== undefined) clearTimeout(hold)
      if (reveal !== undefined) clearTimeout(reveal)
      if (clear !== undefined) clearTimeout(clear)
    }
  }, [targetRef, onDone])

  if (gone) return null

  return (
    <div
      // Not announced. A screen reader already has the wordmark in the nav, and
      // the same two words twice is noise rather than information.
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-[3] flex items-center justify-center overflow-hidden px-8"
    >
      <span
        ref={overlayRef}
        // Sized so the word fits the window it is in. It cannot wrap — a name
        // broken across two lines is not a wordmark — so the type has to shrink
        // instead, and 15vw did not: under about 700px the word was wider than
        // the screen and the overlay clipped both ends of it.
        className="display whitespace-nowrap text-[clamp(2.25rem,13vw,12rem)] leading-none"
        style={{ transformOrigin: 'center center', willChange: 'transform, opacity' }}
      >
        {children}
      </span>
    </div>
  )
}
