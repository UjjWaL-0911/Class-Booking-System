/**
 * Dates and times, formatted for a studio rather than for a browser.
 *
 * The trap this module exists to avoid: `new Date('2026-09-11')` is parsed as
 * midnight **UTC**, so anywhere west of Greenwich it formats as the 10th. Every
 * calendar date in this API — a session's date, a membership expiry — is already
 * a date in the studio's timezone and carries no time at all, so the only correct
 * thing to do with it is read its three numbers and never involve an instant.
 *
 * Instants are the opposite case: `booked_at` and `occurred_at` are real moments,
 * and they must be rendered in the studio's timezone, not the viewer's. A manager
 * checking the desk from a holiday in Lisbon should see the same 08:14 her
 * colleague saw.
 */

import type { Instant, LocalDate, LocalTime } from '@/api/types'

interface DateParts {
  year: number
  month: number
  day: number
}

function parts(date: LocalDate): DateParts {
  const [year = 0, month = 1, day = 1] = date.split('-').map(Number)
  return { year, month, day }
}

/** A Date whose *calendar fields* are the ones in the string. Never an instant. */
function asCalendarDate(date: LocalDate): Date {
  const { year, month, day } = parts(date)
  return new Date(year, month - 1, day)
}

const WEEKDAY_LONG = new Intl.DateTimeFormat('en-GB', { weekday: 'long' })
const WEEKDAY_SHORT = new Intl.DateTimeFormat('en-GB', { weekday: 'short' })
const MONTH_LONG = new Intl.DateTimeFormat('en-GB', { month: 'long' })
const MONTH_SHORT = new Intl.DateTimeFormat('en-GB', { month: 'short' })

/** "Friday 11 September" — the page heading form. */
export function formatDateLong(date: LocalDate): string {
  const value = asCalendarDate(date)
  return `${WEEKDAY_LONG.format(value)} ${value.getDate()} ${MONTH_LONG.format(value)}`
}

/** "Fri 11 Sep" — the table-cell form. */
export function formatDateShort(date: LocalDate): string {
  const value = asCalendarDate(date)
  return `${WEEKDAY_SHORT.format(value)} ${value.getDate()} ${MONTH_SHORT.format(value)}`
}

/** "11 Sep" — no weekday, for columns where the day of the week is noise. */
export function formatDayMonth(date: LocalDate): string {
  const value = asCalendarDate(date)
  return `${value.getDate()} ${MONTH_SHORT.format(value)}`
}

/** "18:00". The seconds the API sends are always zero and never worth the space. */
export function formatTime(time: LocalTime): string {
  return time.slice(0, 5)
}

/** "18:00 to 19:00", from a start time and a duration in minutes. */
export function formatTimeRange(time: LocalTime, durationMin: number): string {
  const [hours = 0, minutes = 0] = time.split(':').map(Number)
  const end = (hours * 60 + minutes + durationMin) % (24 * 60)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${formatTime(time)} to ${pad(Math.floor(end / 60))}:${pad(end % 60)}`
}

/** "11 Sep, 08:14" in the studio's timezone, whatever the viewer's own is. */
export function formatInstant(instant: Instant, timeZone: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone,
  })
    .format(new Date(instant))
    .replace(/,? /, ' ')
    .replace(/(\d{2}:\d{2})$/, ', $1')
}

/** "08:14" only — for a timeline whose date sits in its own column. */
export function formatInstantTime(instant: Instant, timeZone: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    timeZone,
  }).format(new Date(instant))
}

export function formatInstantDay(instant: Instant, timeZone: string): string {
  return new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'short',
    timeZone,
  }).format(new Date(instant))
}

/** Whole days from `from` to `to`, both being calendar dates. */
export function daysBetween(from: LocalDate, to: LocalDate): number {
  const a = asCalendarDate(from).getTime()
  const b = asCalendarDate(to).getTime()
  return Math.round((b - a) / 86_400_000)
}

export function isoDate(value: Date): LocalDate {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
}

/** Shift a calendar date by whole days, staying in calendar space. */
export function addDays(date: LocalDate, days: number): LocalDate {
  const value = asCalendarDate(date)
  value.setDate(value.getDate() + days)
  return isoDate(value)
}

/** The Monday of the week a date falls in. */
export function startOfWeek(date: LocalDate): LocalDate {
  const value = asCalendarDate(date)
  // getDay() puts Sunday at 0; the studio's week starts on Monday, as does the
  // weekday convention the recurrence endpoint uses.
  const offset = (value.getDay() + 6) % 7
  return addDays(date, -offset)
}

/**
 * How a membership expiry should read.
 *
 * Three cases, and the third is the important one: a membership that is fine gets
 * no phrase at all. Labelling every valid membership "expires in 210 days" spends
 * the reader's attention on the eighteen members who need nothing, and leaves the
 * four who do looking the same as the rest.
 */
export function expiryPhrase(daysRemaining: number): string | null {
  if (daysRemaining < 0) {
    const days = Math.abs(daysRemaining)
    return days === 1 ? 'Expired yesterday' : `Expired ${days} days ago`
  }
  if (daysRemaining === 0) return 'Expires today'
  if (daysRemaining === 1) return 'Expires tomorrow'
  if (daysRemaining <= 7) return `Expires in ${daysRemaining} days`
  return null
}
