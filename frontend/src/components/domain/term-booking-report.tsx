import { formatDateShort, formatTime } from '@/lib/dates'
import type { TermBookingOutcome, TermBookingReport } from '@/api/types'

/**
 * What a term booking actually did, session by session.
 *
 * Split from the dialog because it is a different thing on the same screen: the
 * form is what you fill in, this is what you read back, and only one of them is on
 * display when the other is. Keeping them in one file meant a component where half
 * the code was unreachable whenever the other half was visible.
 *
 * Three groups, not two. A full session waitlisting is a *result* — goal 4 working
 * — and burying it with the refusals would tell the desk the wrong thing to say to
 * the member.
 */
const REASONS: Record<string, string> = {
  already_booked: 'Already booked',
  membership_expired: 'Membership had expired',
  session_started: 'Class had already started',
  class_archived: 'Class is archived',
  refused: 'Refused',
}

export function TermBookingReportView({ report }: { report: TermBookingReport }) {
  const nothing = report.requested === 0

  return (
    <div className="flex flex-col gap-6">
      <p className="text-14 leading-[1.6] text-graphite">
        {nothing
          ? 'No sessions of that class fall in the range. Put some on the timetable first, or widen the dates.'
          : `${report.requested} ${report.requested === 1 ? 'session' : 'sessions'} in the range.`}
      </p>

      <Group title="Booked" rows={report.booked} tone="good" />
      <Group title="On the waiting list" rows={report.waitlisted} tone="wait" />
      <Group title="Not booked" rows={report.skipped} tone="bad" />
    </div>
  )
}

function Group({
  title,
  rows,
  tone,
}: {
  title: string
  rows: TermBookingOutcome[]
  tone: 'good' | 'wait' | 'bad'
}) {
  if (rows.length === 0) return null
  const colour =
    tone === 'good' ? 'text-good-ink' : tone === 'wait' ? 'text-wait-ink' : 'text-bad-ink'

  return (
    <section>
      <h3 className={`text-12 font-medium ${colour}`}>
        {title} · {rows.length}
      </h3>
      <ul className="mt-2">
        {rows.map((row) => (
          <li
            key={row.session_id}
            className="flex flex-wrap items-baseline gap-x-4 gap-y-1 border-b border-hairline py-2 last:border-b-0"
          >
            <span className="condensed w-[132px] shrink-0 text-14">
              {formatDateShort(row.session_date)}, {formatTime(row.start_time)}
            </span>
            {row.reason && (
              <span className="text-12 text-graphite">
                {REASONS[row.reason] ?? row.reason}
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
