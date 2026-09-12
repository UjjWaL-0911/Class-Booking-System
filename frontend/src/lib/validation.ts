/**
 * Input rules, mirrored from the backend's Pydantic schemas.
 *
 * **These are a courtesy, not a defence.** Every rule here exists on the server
 * too, and the server's is the one that decides — a client check can be skipped
 * with a browser console and a curl command. What this file buys is that somebody
 * typing a name into a dialog finds out it is too long before they press the
 * button, rather than after a round trip.
 *
 * The limits are duplicated from the schemas on purpose and the numbers are named
 * so the duplication is visible. If one of them changes on the server, this file
 * is where it has to change here — and the check that catches a drift is the
 * server rejecting something this file let through, which surfaces as a
 * `validation_error` with the field named in it, not as silent corruption.
 */

/** Exactly the bounds the Pydantic models declare. */
export const LIMITS = {
  /** members.full_name — min_length=1, max_length=200 */
  fullName: 200,
  /** members.notes — max_length=2000 */
  memberNotes: 2000,
  /** classes.title — min_length=1, max_length=200 */
  classTitle: 200,
  /** classes.discipline — min_length=1, max_length=100 */
  discipline: 100,
  /** classes.description — max_length=2000 */
  description: 2000,
  /** every booking note — max_length=1000 */
  bookingNote: 1000,
  /** rooms.name — min_length=1, max_length=100 */
  roomName: 100,
  /** duration_min — gt=0, le=600 */
  duration: { min: 1, max: 600 },
  /** capacity — gt=0, le=1000 */
  capacity: { min: 1, max: 1000 },
} as const

/**
 * Whether a string is shaped like an email address.
 *
 * Deliberately not an attempt at RFC 5322 — that grammar permits things no studio
 * will ever type and the regexes that implement it are famously unreadable and
 * famously wrong anyway. This asks the three questions that catch every realistic
 * typo: is there exactly one `@`, is there something either side of it, and does
 * the domain have at least one dot with non-empty labels around it.
 *
 * It matches what the server accepts closely enough to be useful and is
 * deliberately a little more permissive, because the failure that matters is this
 * file rejecting an address the server would have taken.
 */
const EMAIL = /^[^\s@]+@[^\s@.]+(\.[^\s@.]+)+$/

/** A rule returns the sentence to show, or null when the value is fine. */
export type Rule = string | null

/**
 * Something had to be typed here.
 *
 * `noun` reads straight into the sentence: `required(v, 'a full name')` produces
 * "Enter a full name." Errors in this app say what to do rather than what went
 * wrong, and never apologise.
 */
export function required(value: string, noun: string): Rule {
  return value.trim() === '' ? `Enter ${noun}.` : null
}

export function emailFormat(value: string): Rule {
  const trimmed = value.trim()
  if (trimmed === '') return 'Enter an email address.'
  if (!EMAIL.test(trimmed)) return 'That is not an email address. It should look like name@example.com.'
  return null
}

/** Counts the trimmed value, since that is what gets sent. */
export function maxLength(value: string, max: number): Rule {
  const length = value.trim().length
  return length > max ? `${max} characters at most. This is ${length}.` : null
}

/**
 * A whole number inside the server's bounds.
 *
 * `optional` is what "leave blank to inherit the class default" needs: an empty
 * box is a valid answer there and means something different from zero.
 */
export function wholeNumber(
  value: string,
  { min, max, optional = false }: { min: number; max: number; optional?: boolean },
): Rule {
  const trimmed = value.trim()
  if (trimmed === '') return optional ? null : 'Enter a number.'

  const parsed = Number(trimmed)
  if (!Number.isFinite(parsed)) return 'Enter a number.'
  if (!Number.isInteger(parsed)) return 'Enter a whole number.'
  if (parsed < min || parsed > max) return `Enter a number between ${min} and ${max}.`
  return null
}

/** A date was chosen at all — an empty date input reads as a valid one otherwise. */
export function dateChosen(value: string, noun: string): Rule {
  return value === '' ? `Choose ${noun}.` : null
}

/** Calendar dates compare correctly as ISO strings, so no parsing is needed. */
export function notBefore(later: string, earlier: string, noun: string): Rule {
  if (later === '' || earlier === '') return null
  return later < earlier ? `This is before ${noun}.` : null
}

/** Something had to be picked from a list. */
export function chosen(value: string, noun: string): Rule {
  return value === '' ? `Choose ${noun}.` : null
}

/** The first rule that fails, so a field shows one sentence rather than three. */
export function firstProblem(...rules: Rule[]): Rule {
  return rules.find((rule) => rule !== null) ?? null
}
