import { formatDayMonth } from '@/lib/dates'
import type { WeekAttendance } from '@/api/types'

/**
 * Eight weeks of attendance (goal 8).
 *
 * Attended and absences stacked, not side by side: the pair is one week's
 * outcome, and two bars per week invites a reader to compare the wrong things.
 * Absences take the same red they take everywhere else in this app, so the
 * colour needs no legend to be understood — though it gets one anyway, because a
 * chart is the one place a mark's meaning cannot be inferred from its row.
 *
 * No gridlines, no y-axis. The figure that matters is printed above its own bar.
 */
export function AttendanceChart({ weeks }: { weeks: WeekAttendance[] }) {
  const totals = weeks.map((week) => week.attended + week.no_show)
  // Guard the divide: eight empty weeks is a legitimate state on a new studio.
  const peak = Math.max(...totals, 1)
  const lastIndex = weeks.length - 1

  return (
    <div className="flex flex-col gap-1">
      <div
        className="grid items-end gap-3.5"
        style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))`, height: 150 }}
      >
        {weeks.map((week, index) => {
          const total = totals[index] ?? 0
          const height = Math.round((total / peak) * 118)
          const noShowHeight = total === 0 ? 0 : Math.round((week.no_show / total) * height)
          const current = index === lastIndex

          return (
            <div key={week.week_start} className="flex h-full flex-col justify-end items-center gap-1.5">
              <span className={current ? 'text-11 font-medium text-ink' : 'text-11 text-graphite'}>
                {total}
              </span>
              <div
                className="flex w-full flex-col justify-end overflow-hidden rounded-t-xs"
                style={{ height: Math.max(height, total > 0 ? 3 : 0) }}
                // The bar is a picture of the number printed above it and the
                // figures in the legend; announcing it twice adds nothing.
                aria-hidden="true"
              >
                {noShowHeight > 0 && (
                  <div className="w-full shrink-0 bg-bad-ink" style={{ height: noShowHeight }} />
                )}
                <div className={current ? 'w-full flex-1 bg-ink' : 'w-full flex-1 bg-mute'} />
              </div>
            </div>
          )
        })}
      </div>

      <div
        className="grid gap-3.5 border-t border-rule pt-2"
        style={{ gridTemplateColumns: `repeat(${weeks.length}, minmax(0, 1fr))` }}
      >
        {weeks.map((week, index) => (
          <span
            key={week.week_start}
            className={
              index === lastIndex
                ? 'text-center text-11 font-medium text-ink'
                : 'text-center text-11 text-graphite'
            }
          >
            {index === lastIndex ? 'This week' : formatDayMonth(week.week_start)}
          </span>
        ))}
      </div>

      <div className="mt-3 flex items-center gap-5 text-11 text-graphite">
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-ink" aria-hidden="true" />
          Attended
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2 rounded-full bg-bad-ink" aria-hidden="true" />
          Absences
        </span>
      </div>
    </div>
  )
}
