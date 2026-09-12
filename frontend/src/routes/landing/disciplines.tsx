import type { ReactNode } from 'react'
import { useOnView } from '@/hooks/use-on-view'
import { cn } from '@/lib/cn'
import { disciplineColor } from '@/lib/vocabulary'

/**
 * What the studio actually runs.
 *
 * The four disciplines in the system, with the thing each one counts. This is
 * where the product stops being abstract: a class is not a row in a table, it is
 * eighteen mats on a floor or eight reformers along a wall, and the number of
 * them is the only reason any of this software exists.
 *
 * The drawings are line art rather than photographs or icons from a set — stroke
 * only, on the same grid, in the discipline's own tint. Equipment seen from the
 * side, which is how you would recognise it across a room.
 */
const DISCIPLINES = [
  {
    name: 'Yoga',
    discipline: 'yoga',
    counts: 'mats',
    typical: 18,
    line: 'A rolled mat per person, and a floor that fills from the front.',
    art: (
      <>
        <rect x="6" y="30" width="52" height="9" rx="4.5" />
        <path d="M14 30v-6a4 4 0 0 1 4-4h28a4 4 0 0 1 4 4v6" />
        <path d="M22 20v-4M32 20v-4M42 20v-4" />
      </>
    ),
  },
  {
    name: 'Cycling',
    discipline: 'cycling',
    counts: 'bikes',
    typical: 12,
    line: 'Twelve bikes, forty-five minutes, and a waiting list by Tuesday.',
    art: (
      <>
        <circle cx="16" cy="34" r="9" />
        <circle cx="48" cy="34" r="9" />
        <path d="M16 34 27 16h8l6 18M27 16h10" />
        <path d="M33 34h15M41 14v6" />
      </>
    ),
  },
  {
    name: 'Dance',
    discipline: 'dance',
    counts: 'places',
    typical: 20,
    line: 'Partner work, so the count is places on the floor rather than kit.',
    art: (
      <>
        <circle cx="24" cy="12" r="4" />
        <path d="M24 16v12l-6 12M24 28l7 11" />
        <path d="M18 22l-7 4M30 22l8-3" />
        <path d="M44 40c6-4 9-10 9-16" />
      </>
    ),
  },
  {
    name: 'Pilates',
    discipline: 'pilates',
    counts: 'reformers',
    typical: 8,
    line: 'Eight reformers and no more, which is why it is always full.',
    art: (
      <>
        <rect x="6" y="22" width="52" height="8" rx="3" />
        <path d="M12 30v8M52 30v8" />
        <rect x="20" y="14" width="18" height="8" rx="3" />
        <path d="M44 18h10M49 14v8" />
      </>
    ),
  },
]

export function Disciplines() {
  const { ref, shown } = useOnView<HTMLElement>()

  return (
    <section ref={ref} className="border-t border-rule">
      <div className="mx-auto max-w-[1220px] px-8 py-32 lg:px-14">
        <Reveal shown={shown} delay={0}>
          <p className="tracked text-11 text-graphite">On the timetable</p>
          <h2 className="display mt-8 max-w-[21ch] text-[clamp(2.25rem,4.4vw,3.5rem)] leading-[1.16]">
            Four disciplines, and a room that can only hold so many.
          </h2>
        </Reveal>

        <div className="mt-20 grid gap-x-10 gap-y-16 sm:grid-cols-2 lg:grid-cols-4">
          {DISCIPLINES.map((item, index) => (
            <Reveal key={item.name} shown={shown} delay={160 + index * 110}>
              <article className="flex flex-col gap-5 border-t border-rule pt-8">
                <svg
                  width="64"
                  height="46"
                  viewBox="0 0 64 46"
                  fill="none"
                  stroke={disciplineColor(item.discipline)}
                  strokeWidth="1.4"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  aria-hidden="true"
                >
                  {item.art}
                </svg>

                <div>
                  <h3 className="display text-36">{item.name}</h3>
                  <p className="tracked mt-2 text-11 text-graphite">
                    {item.typical} {item.counts}
                  </p>
                </div>

                <p className="max-w-[28ch] text-14 leading-[1.7] text-graphite text-pretty">
                  {item.line}
                </p>
              </article>
            </Reveal>
          ))}
        </div>
      </div>
    </section>
  )
}

/** Holds its children until the section is seen, then rises them in sequence. */
function Reveal({
  shown,
  delay,
  children,
}: {
  shown: boolean
  delay: number
  children: ReactNode
}) {
  return (
    <div
      className={cn('on-view', shown && 'is-visible')}
      style={{ '--reveal-delay': `${delay}ms` } as React.CSSProperties}
    >
      {children}
    </div>
  )
}
