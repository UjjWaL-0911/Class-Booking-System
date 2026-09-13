import { useEffect } from 'react'
import { QueryClientProvider } from '@tanstack/react-query'
import { createBrowserRouter, Navigate, RouterProvider } from 'react-router-dom'
import { restoreSession } from '@/api/client'
import { ToastProvider } from '@/components/ui/toast'
import { createQueryClient } from '@/lib/query-client'
import { routes } from '@/lib/routes'
import { AppShell } from '@/layout/app-shell'
import { RequireSession } from '@/layout/require-session'
import { LandingPage } from '@/routes/landing/landing'
import { PublicSchedulePage } from '@/routes/schedule'
import { SignInPage } from '@/routes/sign-in'
import { TodayPage } from '@/routes/today'
import { TimetablePage } from '@/routes/timetable'
import { SessionDetailPage } from '@/routes/session-detail'
import { BookingsPage } from '@/routes/bookings'
import { BookingHistoryPage } from '@/routes/booking-history'
import { MembersPage } from '@/routes/members'
import { PeoplePage } from '@/routes/people'
import { ClassesPage } from '@/routes/classes'
import { ReportsPage } from '@/routes/reports'

const queryClient = createQueryClient()

/**
 * Three tiers, and the split is about who the page is for.
 *
 * `/` is the landing page and is public — it makes the case for the software and
 * never asks for a password. `/sign-in` is the door. Everything the studio
 * actually uses lives under `/app`, behind the session gate.
 *
 * The tool moved under a prefix when the landing page took the root, which is
 * exactly the kind of change that strands one forgotten link. Every path in the
 * app now comes from `lib/routes`, so there is one place to be wrong rather than
 * thirty.
 */
const router = createBrowserRouter([
  { path: routes.landing, element: <LandingPage /> },
  { path: routes.signIn, element: <SignInPage /> },
  // Public, like the landing page: no session required, and deliberately
  // outside RequireSession so a stranger is never bounced to sign-in.
  { path: routes.schedule, element: <PublicSchedulePage /> },
  {
    element: <RequireSession />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: routes.today, element: <TodayPage /> },
          { path: routes.timetable, element: <TimetablePage /> },
          { path: '/app/sessions/:sessionId', element: <SessionDetailPage /> },
          { path: routes.bookings, element: <BookingsPage /> },
          { path: '/app/bookings/:bookingId', element: <BookingHistoryPage /> },
          { path: routes.members, element: <MembersPage /> },
          { path: routes.classes, element: <ClassesPage /> },
          { path: routes.people, element: <PeoplePage /> },
          { path: routes.reports, element: <ReportsPage /> },
        ],
      },
    ],
  },
  // Anything unrecognised goes to the landing page rather than the tool: an
  // unknown path is more likely to be somebody arriving than somebody lost
  // inside.
  { path: '*', element: <Navigate to={routes.landing} replace /> },
])

export function App() {
  // The access token does not survive a reload — it is held in a module variable
  // on purpose — but the refresh cookie does. This asks the server to turn that
  // cookie back into a session, which is the only thing standing between
  // refreshing the page and being shown the sign-in form.
  //
  // It deliberately does *not* gate the router. The landing page is public and
  // has nothing to do with a session; blocking it on a round trip would mean an
  // anonymous visitor staring at a holding screen while a cold server wakes up,
  // on the one page whose whole job is a good first impression. The routes that
  // genuinely need an answer wait for it themselves — the session store starts
  // in `unknown`, and both the gate and the sign-in page know what to do with it.
  useEffect(() => {
    void restoreSession()
  }, [])

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <RouterProvider router={router} />
      </ToastProvider>
    </QueryClientProvider>
  )
}
