import type { ReactNode } from 'react'
import { Outlet } from 'react-router-dom'
import { Rail } from './rail'
import { StudioProvider } from '@/studio/studio-provider'
import { BootScreen, ErrorState } from '@/components/ui/states'

/**
 * One surface, with navigation standing on the left of it.
 *
 * No seam anywhere: the rail, the content and the page are the same ground, and
 * what separates them is distance. The content column is capped so a table does
 * not stretch to two thousand pixels on a wide monitor, but it is left-aligned
 * rather than centred — this is a tool read down the left edge, and a column that
 * drifts with the window width makes every row start somewhere new.
 *
 * `StudioProvider` sits inside the gate rather than outside it because it needs a
 * signed-in caller: it establishes the studio's timezone and the studio's idea of
 * today, and every date below is formatted against those two facts rather than
 * the viewer's own clock.
 */
export function AppShell() {
  return (
    <div className="flex min-h-screen bg-paper">
      <Rail />
      <main className="min-w-0 flex-1">
        <StudioProvider
          fallback={<BootScreen>Opening the studio</BootScreen>}
          onError={(error) => (
            <div className="px-14 py-12">
              <ErrorState error={error} onRetry={() => window.location.reload()} />
            </div>
          )}
        >
          <Outlet />
        </StudioProvider>
      </main>
    </div>
  )
}

/**
 * The page frame.
 *
 * Generous, and deliberately more generous than a dense tool usually gets: the
 * boxes that used to separate one region from another are gone, so the space
 * between them is now the only thing doing that job and it has to be big enough
 * to be read as structure rather than as a gap.
 */
export function Page({ children }: { children: ReactNode }) {
  return (
    <div className="flex max-w-[1180px] flex-col gap-12 px-14 pb-24 pt-10">{children}</div>
  )
}

/**
 * Heading, one line of context, actions on the right.
 *
 * The title is the display serif — one per screen, and the only place in the tool
 * it appears. It is what ties these pages to the landing page without putting a
 * Didone anywhere near a column of times, where its hairlines would vanish and
 * its proportions would fight the tabular figures.
 */
export function PageHeader({
  title,
  subtitle,
  actions,
  back,
}: {
  title: string
  subtitle?: ReactNode
  actions?: ReactNode
  back?: ReactNode
}) {
  return (
    <div className="flex flex-col gap-6">
      {back}
      <div className="flex items-end justify-between gap-8">
        <div className="min-w-0">
          <h1 className="display text-36">{title}</h1>
          {subtitle && <div className="mt-2 text-12 text-graphite">{subtitle}</div>}
        </div>
        {actions && <div className="flex shrink-0 gap-2">{actions}</div>}
      </div>
    </div>
  )
}
