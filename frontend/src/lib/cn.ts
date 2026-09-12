/**
 * Join class names, dropping anything falsy.
 *
 * Not `clsx`, and not `tailwind-merge`. This app has no runtime class conflicts
 * to resolve — variants are chosen in one place per component and never layered
 * — so a dependency that parses Tailwind syntax at runtime would buy nothing and
 * cost a bundle.
 */
export function cn(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(' ')
}
