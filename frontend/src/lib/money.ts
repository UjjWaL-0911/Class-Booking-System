/**
 * Money, as integer minor units.
 *
 * The server sends and accepts paise/pence/cents as whole numbers and never a
 * decimal — money in a float is a rounding error waiting for a year-end total.
 * These two functions are the only places in the app where that representation is
 * converted, and `toMinor` deliberately does its arithmetic on the digits rather
 * than on `parseFloat(...) * 100`, which turns 12.10 into 1209.9999999999998.
 *
 * No currency symbol anywhere. This system has never been told which currency the
 * studio keeps its books in, and inventing one on a payroll figure is worse than
 * printing the number bare.
 */

/** Minor units to something a person reads: `120000` → `1,200.00`. */
export function formatMoney(minor: number): string {
  return (minor / 100).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

/** The largest value the column holds — a 32-bit integer. Mirrors the server. */
export const MAX_RATE_MINOR = 2_147_483_647

/**
 * What somebody typed, as minor units.
 *
 * Three outcomes rather than two, because an empty box is not an error: it is how
 * a rate is *cleared*, which is a real thing to do and different from typing a
 * zero. `null` means "no rate", `undefined` means "that is not a number".
 */
export function toMinor(typed: string): number | null | undefined {
  const cleaned = typed.replace(/[\s,]/g, '')
  if (cleaned === '') return null
  if (!/^\d+(\.\d{1,2})?$/.test(cleaned)) return undefined

  const [whole, fraction = ''] = cleaned.split('.')
  const minor = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  return minor > MAX_RATE_MINOR ? undefined : minor
}

/** Minor units back into the box, for editing: `120000` → `1200.00`. */
export function toTyped(minor: number | null): string {
  return minor === null ? '' : (minor / 100).toFixed(2)
}
