/**
 * The studio's words and colours, kept apart from the components that use them.
 *
 * These are pure domain vocabulary rather than presentation: what a spot in the
 * room is called, what a queue position reads as, which tint belongs to a
 * discipline. Several components need each of them, and none of them owns any.
 */

/**
 * What the spots in the room are called, by discipline.
 *
 * Worth the four lines: "10 of 12 bikes" is how the studio talks, and an
 * interface that says "10 of 12 spots" to a cycling instructor is an interface
 * written by somebody who has not been in the room.
 */
export function spotNoun(discipline: string, plural = true): string {
  const noun = { yoga: 'mat', cycling: 'bike', pilates: 'reformer' }[discipline.toLowerCase()]
  if (!noun) return plural ? 'spots' : 'spot'
  return plural ? `${noun}s` : noun
}

/** "1st", "2nd" — a queue position reads as a place, not a quantity. */
export function ordinal(value: number): string {
  const suffix =
    value % 100 >= 11 && value % 100 <= 13 ? 'th' : (['th', 'st', 'nd', 'rd'][value % 10] ?? 'th')
  return `${value}${suffix}`
}

/**
 * Discipline tints, used as a 3px left edge and nowhere else.
 *
 * They identify a class at a glance on a list of a dozen sessions. Desaturated
 * hard, because the moment a tint competes with a status chip in the same row it
 * has stopped being an aid and become noise.
 */
const DISCIPLINE_COLOR: Record<string, string> = {
  yoga: 'var(--color-yoga)',
  cycling: 'var(--color-cycling)',
  dance: 'var(--color-dance)',
  pilates: 'var(--color-pilates)',
}

export function disciplineColor(discipline: string): string {
  return DISCIPLINE_COLOR[discipline.toLowerCase()] ?? 'var(--color-discipline)'
}
