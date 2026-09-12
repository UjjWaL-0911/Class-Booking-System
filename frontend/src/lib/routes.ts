/**
 * Every path in the app, in one place.
 *
 * The tool moved under `/app` when the landing page took `/`, and that is exactly
 * the kind of change that leaves one forgotten `to="/bookings"` navigating a
 * signed-in user back out to the marketing page. Naming the routes once makes
 * that impossible to get wrong and the next move trivial.
 */
const APP = '/app'

export const routes = {
  /** Public. The landing page, which is not the sign-in page. */
  landing: '/',
  signIn: '/sign-in',

  today: APP,
  timetable: `${APP}/timetable`,
  bookings: `${APP}/bookings`,
  members: `${APP}/members`,
  classes: `${APP}/classes`,
  reports: `${APP}/reports`,

  session: (id: string) => `${APP}/sessions/${id}`,
  bookingHistory: (id: string) => `${APP}/bookings/${id}`,

  /** Pre-filtered lists, which several screens link into. */
  sessionsForClass: (classId: string) => `${APP}/timetable?class=${classId}`,
  bookingsForClass: (classId: string) => `${APP}/bookings?class=${classId}`,
  bookingsWithStatus: (status: string) => `${APP}/bookings?status=${status}`,
  bookingsFor: (email: string) => `${APP}/bookings?q=${encodeURIComponent(email)}`,
  memberSearch: (email: string) => `${APP}/members?q=${encodeURIComponent(email)}`,
} as const
