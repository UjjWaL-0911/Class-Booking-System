import { PanelHeader } from '@/components/ui/panel'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useIsStaff } from '@/hooks/use-auth'
import { useOperations } from '@/hooks/use-operations'
import { formatDateShort } from '@/lib/dates'
import type { InstructorPay, RoomUsage } from '@/api/types'

/**
 * Room utilisation and instructor pay, over one window.
 *
 * Two stretch ideas, one request, one component — they are read together and they
 * answer two halves of the same question: what did the studio actually run, and
 * what did it cost.
 *
 * **Hours, not a percentage.** A percentage needs opening hours, and nobody has
 * told this system what those are. Each room is drawn against the busiest one
 * instead, which answers "which room is under-used" without anybody having to
 * agree what 100% would mean.
 *
 * **Money is formatted here and nowhere else.** The server sends minor units as
 * integers throughout — the only division by 100 in the system is on the line
 * below, at the moment it is printed.
 *
 * **An instructor sees one half of it**: their own pay, no utilisation, no
 * colleagues. The server has already scoped the response, so the only thing the
 * role changes here is the wording and the column count — a screen that says
 * "Instructor pay" over a list of one, next to an empty rooms panel, would be
 * technically correct and read as a bug.
 */
export function OperationsPanels({ from, to }: { from: string; to: string }) {
  const report = useOperations(from, to)
  const isStaff = useIsStaff()

  if (report.isPending) return <Skeleton rows={6} />
  if (report.error) {
    return <ErrorState error={report.error} onRetry={() => void report.refetch()} />
  }
  if (!report.data) return null

  const { rooms, instructors, payroll_total_minor: total } = report.data
  const window = `${formatDateShort(from)} to ${formatDateShort(to)}`

  return (
    <div className={isStaff ? 'grid grid-cols-1 items-start gap-8 xl:grid-cols-2' : undefined}>
      {isStaff && (
        <section>
          <PanelHeader label="Room use" aside={window} />
          {rooms.length === 0 ? (
            <EmptyState title="No rooms yet">
              Rooms are what sessions are scheduled into.
            </EmptyState>
          ) : (
            <ul>
              {rooms.map((room) => (
                <RoomRow key={room.room_id} room={room} peak={peakMinutes(rooms)} />
              ))}
            </ul>
          )}
        </section>
      )}

      <section>
        <PanelHeader
          label={isStaff ? 'Instructor pay' : 'Your pay'}
          /* The total is the studio's payroll bill. For an instructor it would be
             their own row printed twice, so they get the window instead. */
          aside={
            !isStaff
              ? window
              : total === null
                ? 'Total withheld — a rate is missing'
                : formatMoney(total)
          }
        />
        {instructors.length === 0 ? (
          <EmptyState title={isStaff ? 'Nobody taught in this window' : 'You taught nothing here'}>
            {isStaff
              ? 'Pay is counted from sessions led, so an empty timetable means an empty list.'
              : 'Pay is counted from the sessions you lead, not the ones you assist on.'}
          </EmptyState>
        ) : (
          <ul>
            {instructors.map((person) => (
              <PayRow key={person.instructor_id} person={person} />
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}

function RoomRow({ room, peak }: { room: RoomUsage; peak: number }) {
  const share = peak === 0 ? 0 : (room.minutes_booked / peak) * 100

  return (
    <li className="flex h-11 items-center gap-4 border-b border-hairline last:border-b-0">
      <span className="w-[140px] shrink-0 truncate text-14">{room.room_name}</span>
      <span className="flex-1" aria-hidden="true">
        <span
          className="block h-1.5 rounded-full bg-mute"
          style={{ width: `${Math.max(share, room.minutes_booked > 0 ? 2 : 0)}%` }}
        />
      </span>
      <span className="w-[92px] shrink-0 text-right text-12 text-graphite">
        {room.sessions === 0 ? 'unused' : `${formatHours(room.minutes_booked)} · ${room.sessions}`}
      </span>
    </li>
  )
}

function PayRow({ person }: { person: InstructorPay }) {
  return (
    <li className="flex h-11 items-center gap-4 border-b border-hairline last:border-b-0">
      <span className="min-w-0 flex-1 truncate text-14">{person.instructor_name}</span>
      <span className="w-[110px] shrink-0 text-right text-12 text-graphite">
        {person.sessions_taught} · {formatHours(person.minutes_taught)}
      </span>
      <span className="w-[104px] shrink-0 text-right text-14 font-medium">
        {/* Null is not zero. "No rate set" is a thing somebody has to go and fix;
            "owed nothing" is a number. Printing the second for the first is how a
            person gets underpaid quietly. */}
        {person.total_minor === null ? (
          <span className="text-12 font-normal text-wait-ink">no rate</span>
        ) : (
          formatMoney(person.total_minor)
        )}
      </span>
    </li>
  )
}

function peakMinutes(rooms: RoomUsage[]): number {
  return Math.max(...rooms.map((room) => room.minutes_booked), 1)
}

function formatHours(minutes: number): string {
  if (minutes === 0) return '0h'
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest}m`
  return rest === 0 ? `${hours}h` : `${hours}h ${rest}m`
}

/**
 * Minor units to something a person reads.
 *
 * Grouped by `toLocaleString` rather than by hand, and deliberately with no
 * currency symbol: the server has never been told which currency the studio keeps
 * its books in, and inventing one on a payroll report is worse than leaving the
 * number bare.
 */
function formatMoney(minor: number): string {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}
