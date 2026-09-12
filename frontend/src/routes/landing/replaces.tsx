import type { CSSProperties } from 'react'
import { useOnView } from '@/hooks/use-on-view'
import { cn } from '@/lib/cn'

/**
 * What the software is *for*, stated as the three paper things it takes away.
 *
 * Not a feature list. The brief describes a studio with a sign-up sheet on a
 * clipboard and a membership binder behind the desk, and every one of these is a
 * specific failure of those objects rather than a capability with a tick beside
 * it. "Automatic waiting lists" is a feature; "the sheet cannot tell anyone a
 * place opened up" is the reason somebody would want one.
 *
 * Numbered, because a numbered marker is only honest when the content is a
 * sequence or a set — and this is a closed set of three, counted deliberately.
 */
const ITEMS = [
  {
    paper: 'The sign-up sheet',
    heading: 'A roster that knows how many mats are left',
    body: 'Every class carries its capacity as a row of marks — one for each mat, bike or reformer in the room. Full is something you see rather than something you count. Two people at two screens cannot take the same last place; the database settles it, not the interface.',
  },
  {
    paper: 'The waiting list in the margin',
    heading: 'A queue that moves on its own',
    body: 'When somebody cancels, the place goes to whoever was first in line — immediately, and without anybody being asked. Expired memberships are passed over rather than promoted, and the booking’s history records that a place was offered and skipped, so nothing about it has to be remembered.',
  },
  {
    paper: 'The membership binder',
    heading: 'Expiry dates that come to you',
    body: 'Memberships lapsing in the next week appear on the desk’s first screen, already sorted with the ones that have run out at the top. Nobody has to leaf through anything, and a lapsed member cannot quietly be booked into a class.',
  },
]

export function Replaces() {
  const { ref, shown } = useOnView<HTMLElement>()

  return (
    <section
      ref={ref}
      id="what-it-replaces"
      className="mx-auto max-w-[1220px] px-8 py-32 lg:px-14"
    >
      <p className="tracked text-11 text-graphite">What it replaces</p>

      <div className="mt-16 flex flex-col gap-20">
        {ITEMS.map((item, index) => (
          <article
            key={item.paper}
            className={cn(
              // The middle column has a floor rather than a share. As a bare `1fr` it
              // shrank to whatever was left, and the phrases in it are the longest
              // short text on the page — thirty characters for the waiting list one.
              'on-view grid gap-8 border-t border-rule pt-10 lg:gap-14',
              'lg:grid-cols-[auto_minmax(15rem,0.85fr)_1.6fr]',
              shown && 'is-visible',
            )}
            style={{ '--reveal-delay': `${index * 140}ms` } as CSSProperties}
          >
            <span className="display text-36 text-mute">
              {String(index + 1).padStart(2, '0')}
            </span>

            <div>
              <p className="tracked text-11 text-graphite">Instead of</p>
              {/* No strikethrough. These read as crossed out because they were —
                  a line through the paper object seemed like a neat way to say
                  "not this any more", and instead it read as text rendered
                  wrong. The label above already says "Instead of", which is the
                  whole job, so the line was decoration that cost legibility. */}
              <p className="mt-3 text-16 text-graphite text-balance">{item.paper}</p>
            </div>

            <div>
              <h3 className="display max-w-[26ch] text-[clamp(1.6rem,2.4vw,2.1rem)] leading-[1.3]">
                {item.heading}
              </h3>
              <p className="mt-5 max-w-[60ch] text-14 leading-[1.75] text-graphite text-pretty">
                {item.body}
              </p>
            </div>
          </article>
        ))}
      </div>
    </section>
  )
}
