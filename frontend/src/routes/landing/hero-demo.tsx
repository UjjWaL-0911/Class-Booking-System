import { useEffect, useState } from 'react'

/**
 * The hero's image, and it is the product rather than a photograph.
 *
 * The reference this page was designed against puts a laptop behind the
 * headline — the thing being sold, softened and out of focus. There is no
 * photography here and inventing some would be worse than not having it, so the
 * same job is done by the one element this whole interface is built around: the
 * occupancy marks, drawn large.
 *
 * It runs once, on a loop, and it is the single piece of unprompted motion in the
 * product. What it shows is the sequence that a paper sign-up sheet cannot do at
 * all — a class filling, reaching capacity, someone dropping out, and the next
 * person in line taking the place automatically. That is the argument for the
 * software, made without a sentence.
 *
 * `prefers-reduced-motion` stops it on the full class, which is the frame that
 * carries the point.
 */
const CAPACITY = 18

/** Mats taken at each beat. The dip is the cancellation; the recovery is the promotion. */
const BEATS = [5, 8, 11, 14, 16, 17, 18, 18, 18, 17, 18, 18]

export function HeroDemo() {
  const [beat, setBeat] = useState(0)

  useEffect(() => {
    const reduced =
      typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) {
      setBeat(BEATS.indexOf(18))
      return
    }

    const timer = setInterval(() => setBeat((current) => (current + 1) % BEATS.length), 900)
    return () => clearInterval(timer)
  }, [])

  const taken = BEATS[beat] ?? CAPACITY
  const promoted = beat > 0 && (BEATS[beat - 1] ?? 0) < taken && taken === CAPACITY

  return (
    <div
      className="flex w-full max-w-[420px] flex-col gap-5 text-left"
      aria-hidden="true"
    >
      <div className="flex items-baseline justify-between">
        <div>
          <p className="display text-28 text-ink">Vinyasa Flow</p>
          <p className="tracked mt-1.5 text-11 text-graphite">Friday, 18:00 · Studio A</p>
        </div>
        <p className="condensed text-36 font-semibold text-ink" style={{ lineHeight: 1 }}>
          {taken}
          <span className="text-14 font-normal text-graphite"> / {CAPACITY}</span>
        </p>
      </div>

      <div className="flex flex-wrap gap-2">
        {Array.from({ length: CAPACITY }, (_, index) => (
          <span
            key={index}
            className="size-3 rounded-full transition-colors duration-500"
            style={{
              background: index < taken ? 'var(--color-ink)' : 'transparent',
              boxShadow: index < taken ? 'none' : 'inset 0 0 0 1px var(--color-mute)',
            }}
          />
        ))}
      </div>

      <p
        className="text-12 transition-opacity duration-500"
        style={{ color: promoted ? 'var(--color-wait-ink)' : 'var(--color-graphite)', opacity: taken === CAPACITY ? 1 : 0.75 }}
      >
        {promoted
          ? 'A mat opened. The top of the waiting list took it.'
          : taken === CAPACITY
            ? 'Full. Four people waiting.'
            : `${CAPACITY - taken} mats free`}
      </p>
    </div>
  )
}
