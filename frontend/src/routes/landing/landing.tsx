import { useCallback, useRef, useState, type CSSProperties } from 'react'
import { Link } from 'react-router-dom'
import { Disciplines } from './disciplines'
import { HeroDemo } from './hero-demo'
import { useSession } from '@/hooks/use-auth'
import { Replaces } from './replaces'
import { StudioIntro } from './studio-intro'
import { routes } from '@/lib/routes'

/**
 * The landing page.
 *
 * Designed against a reference the client supplied, and the things taken from it
 * are deliberate: a dark ground with the product behind the words rather than a
 * card on a page; navigation that is transparent and has no bar at all; a
 * high-contrast display serif at a size that would be absurd anywhere else;
 * tracked capitals on the navigation and the calls to action; one thin warm
 * hairline as the only colour, and monochrome everywhere else.
 *
 * What was *not* taken is the centred composition. The reference centres a
 * headline over a photograph; here there is a live demonstration to stand beside
 * it, and putting the words over the marks would have buried both.
 *
 * The whole page is one ground, and it is light in both of the app's themes.
 * Somebody arriving has no relationship with this product yet, so the first
 * thing they see should be the thing it was designed to be rather than whatever
 * their laptop decided at dusk.
 *
 * The name arrives filling the screen and shrinks into the nav before anything
 * else appears — see `StudioIntro`. Everything below it is held back until then,
 * so the staged reveal begins as the name lands rather than competing with it.
 *
 * This is not the sign-in page, and it never asks for a password. It makes the
 * case, and then points at the door.
 */
export function LandingPage() {
  // Somebody already signed in can reach this page — it is public, and the
  // browser remembers addresses. Sending them to a sign-in form they do not need
  // would be the interface forgetting who it is talking to.
  const { status } = useSession()
  const signedIn = status === 'signed-in'
  // The buttons always say "Open the studio" — that is what pressing them does
  // either way. Only the quiet nav link changes, because "Sign in" is a
  // promise the page cannot keep for somebody who already has.
  const door: Door = {
    to: signedIn ? routes.today : routes.signIn,
    label: signedIn ? 'The studio' : 'Sign in',
  }

  // The wordmark in the nav is the intro's destination, so it has to be laid out
  // and measurable before the flight starts — it is rendered from the first
  // frame and simply kept invisible until the name lands on it.
  const markRef = useRef<HTMLSpanElement>(null)
  const [arrived, setArrived] = useState(false)
  const land = useCallback(() => setArrived(true), [])

  return (
    <div className="scheme-landing relative min-h-screen">
      {/* The light, in three pools: one lightens, two darken, all sized by
          arithmetic so neither the brightest nor the darkest place they make can
          drop anything below its contrast floor. The `overflow-hidden` belongs
          here and only here — the pools sit past the edges on purpose, and this
          is what stops them widening the document. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        {POOLS.map((pool) => (
          <span key={pool.className} className={pool.className} style={{ background: pool.background }} />
        ))}
      </div>

      <StudioIntro targetRef={markRef} onDone={land}>
        Mornington Studios
      </StudioIntro>

      <div className="relative">
        <Hero door={door} markRef={markRef} arrived={arrived} />
        {/* Mounted on arrival rather than merely hidden. While the hero is
            collapsed to its nav these sections sit inside the viewport, so their
            scroll observers would fire and reveal them behind the name. Mounting
            late puts them below the fold, where the observer belongs. */}
        {arrived && (
          <>
            <Disciplines />
            <Replaces />
            <Closing door={door} />
          </>
        )}
      </div>
    </div>
  )
}

/** Three light sources, sized by arithmetic rather than by eye. */
const POOLS = [
  {
    className: 'pool-a absolute -right-[12%] -top-[24%] h-[940px] w-[940px] rounded-full',
    background: 'radial-gradient(circle, rgb(255 249 236 / 0.55) 0%, transparent 62%)',
  },
  {
    className: 'pool-b absolute -bottom-[16%] -left-[18%] h-[840px] w-[840px] rounded-full',
    background: 'radial-gradient(circle, rgb(198 150 84 / 0.10) 0%, transparent 64%)',
  },
  {
    className: 'pool-c absolute left-[24%] top-[36%] h-[780px] w-[780px] rounded-full',
    background: 'radial-gradient(circle, rgb(120 125 175 / 0.07) 0%, transparent 66%)',
  },
]

interface Door {
  to: string
  label: string
}

function Hero({
  door,
  markRef,
  arrived,
}: {
  door: Door
  markRef: React.RefObject<HTMLSpanElement | null>
  /** False until the intro has flown the name into place. */
  arrived: boolean
}) {
  return (
    <header className="relative">
      <nav
        className="reveal relative mx-auto flex max-w-[1220px] items-center justify-between px-8 py-8 lg:px-14"
        style={{ '--reveal-delay': '60ms' } as CSSProperties}
      >
        {/* The largest thing in this bar, and it should be: everything beside it
            is a signpost, and this is the name. Also where the intro lands — the
            flight is measured at both ends, so resizing it needs nothing else. */}
        <span
          ref={markRef}
          className="display text-36 leading-none transition-opacity duration-200 sm:text-44"
          style={{ opacity: arrived ? 1 : 0 }}
        >
          Mornington Studios
        </span>
        <div
          className="flex items-center gap-10 transition-opacity duration-300"
          style={{ opacity: arrived ? 1 : 0 }}
        >
          <a
            href="#what-it-replaces"
            className="tracked hidden text-11 text-graphite transition-colors duration-[120ms] hover:text-ink sm:block"
          >
            What it replaces
          </a>
          {/* The one link on this page that shows the product rather than
              describing it. Worth a place in the nav for that reason alone. */}
          <Link
            to={routes.schedule}
            className="tracked text-11 text-graphite transition-colors duration-[120ms] hover:text-ink"
          >
            This week
          </Link>
          <Link
            to={door.to}
            className="tracked text-11 text-graphite transition-colors duration-[120ms] hover:text-ink"
          >
            {door.label}
          </Link>
        </div>
      </nav>

      {arrived && (
      <div className="relative mx-auto grid max-w-[1220px] items-center gap-16 px-8 pb-28 pt-16 lg:grid-cols-[1.15fr_1fr] lg:px-14 lg:pb-36 lg:pt-24">
        <div>
          <h1
            className="reveal display max-w-[15ch] text-[clamp(3rem,8vw,6rem)] leading-[1.12]"
            style={{ textWrap: 'balance', '--reveal-delay': '200ms' } as CSSProperties}
          >
            The sign-up sheet, retired.
          </h1>

          <p
            className="reveal mt-8 max-w-[46ch] text-16 leading-[1.65] text-graphite text-pretty"
            style={{ '--reveal-delay': '320ms' } as CSSProperties}
          >
            Classes, memberships, waiting lists and attendance for a studio that has outgrown the
            clipboard. One screen at the front desk, and the same one in an instructor's hand.
          </p>

          <div
            className="reveal mt-12 flex flex-wrap items-center gap-8"
            style={{ '--reveal-delay': '440ms' } as CSSProperties}
          >
            <Link
              to={door.to}
              className="tracked border border-brass px-9 py-4 text-11 text-ink transition-colors duration-[120ms] hover:bg-brass hover:text-paper"
            >
              Open the studio
            </Link>

            <a href="#what-it-replaces" className="group flex items-center gap-4">
              <span className="flex size-11 items-center justify-center rounded-full border border-rule transition-colors duration-[120ms] group-hover:border-ink">
                <svg width="9" height="11" viewBox="0 0 9 11" fill="currentColor" aria-hidden="true">
                  <path d="M0 0.5v10l9-5z" />
                </svg>
              </span>
              <span className="tracked text-11 text-graphite transition-colors duration-[120ms] group-hover:text-ink">
                See what it does
              </span>
            </a>
          </div>
        </div>

        <div
          className="reveal flex justify-start lg:justify-end"
          style={{ '--reveal-delay': '560ms' } as CSSProperties}
        >
          <HeroDemo />
        </div>
      </div>
      )}
    </header>
  )
}

/**
 * The way in, and nothing else.
 *
 * This closed with a headline and a paragraph of persuasion after two sections of
 * it; by the time somebody has read this far they have decided. It also carried
 * the demo addresses and password, which a public page of a live product would
 * never print — those are in SUBMISSION.md, where a reviewer reads and a crawler
 * does not.
 */
function Closing({ door }: { door: Door }) {
  return (
    <section className="mx-auto max-w-[1220px] px-8 pb-32 pt-8 lg:px-14">
      <div className="border-t border-rule pt-16">
        <div className="flex flex-wrap items-center gap-8">
          <Link
            to={door.to}
            className="tracked inline-block border border-brass px-9 py-4 text-11 text-ink transition-colors duration-[120ms] hover:bg-brass hover:text-paper"
          >
            Open the studio
          </Link>
          <Link
            to={routes.schedule}
            className="tracked text-11 text-graphite underline decoration-1 underline-offset-4 transition-colors duration-[120ms] hover:text-ink"
          >
            See what is on
          </Link>
        </div>
      </div>
    </section>
  )
}
