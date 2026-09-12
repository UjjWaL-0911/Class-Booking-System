import { formatDateShort, formatTime } from '@/lib/dates'
import type { GenerationReport, SkipReason } from '@/api/types'

const SKIP_LABEL: Record<SkipReason, string> = {
  room_busy: 'Room already booked',
  instructor_busy: 'Instructor already teaching',
  nonexistent_local_time: 'That clock time does not exist',
}

/**
 * What the generator did, and — the half that matters — what it would not do.
 *
 * Goal 7 asks for a result that "reports which sessions were created and which
 * were skipped because the chosen instructor or room was already booked in an
 * overlapping window". So every skipped date is named with the reason beside it
 * and the server's own sentence underneath, which says what it collided with.
 * This stays on screen until it is dismissed; a toast would vanish while somebody
 * was still reading the third line.
 */
export function GenerationReportView({ report }: { report: GenerationReport }) {
  return (
    <div className="flex flex-col gap-5">
      <p className="text-14 text-graphite text-pretty">
        <span className="font-semibold text-ink">{report.created.length}</span> of{' '}
        <span className="font-semibold text-ink">{report.requested}</span>{' '}
        {report.requested === 1 ? 'date was' : 'dates were'} added to the timetable
        {report.skipped.length > 0 && (
          <>
            , and <span className="font-semibold text-ink">{report.skipped.length}</span>{' '}
            {report.skipped.length === 1 ? 'was' : 'were'} skipped
          </>
        )}
        .
      </p>

      {report.skipped.length > 0 && (
        <div className="rounded-sm border border-rule">
          <p className="border-b border-rule px-4 py-2.5 text-12 font-medium text-graphite">
            Skipped
          </p>
          <ul>
            {report.skipped.map((skip, index) => (
              <li
                key={`${skip.session_date}-${index}`}
                className="flex flex-col gap-0.5 border-b border-hairline px-4 py-2.5 last:border-b-0"
              >
                <div className="flex items-center justify-between gap-4">
                  <span className="text-14 font-medium">
                    {formatDateShort(skip.session_date)}, {formatTime(skip.start_time)}
                  </span>
                  <span className="shrink-0 rounded-xs bg-wait-wash px-[7px] py-[3px] text-11 font-medium text-wait-ink">
                    {SKIP_LABEL[skip.reason]}
                  </span>
                </div>
                <span className="text-12 text-graphite text-pretty">{skip.detail}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.created.length > 0 && (
        <p className="text-12 text-graphite">
          The new sessions are on the timetable from{' '}
          {formatDateShort(report.created[0]!.session_date)}.
        </p>
      )}
    </div>
  )
}
