import { QueryClient } from '@tanstack/react-query'
import { ApiError } from '@/api/errors'

/**
 * Retry policy, which is a domain decision here rather than a default.
 *
 * Most failures in this app are the server saying no on purpose — a membership
 * has expired, a session is full, a version is stale. Retrying those is pointless
 * and, worse, it delays the message the person at the desk needs to read.
 *
 * The exception is `lock_timeout`. Two people booking the last spot on the same
 * session contend for one row lock, and the loser gets a 503 with `Retry-After`.
 * That one genuinely succeeds on a second attempt about a second later, which is
 * exactly the case retries exist for.
 */
function shouldRetry(failureCount: number, error: unknown): boolean {
  if (!(error instanceof ApiError)) return false
  if (!error.isRetryable) return false
  return failureCount < 2
}

function retryDelay(attempt: number, error: unknown): number {
  // The server states how long to wait; honour it rather than guessing.
  if (error instanceof ApiError && error.retryAfterSeconds !== null) {
    return error.retryAfterSeconds * 1000
  }
  return Math.min(1000 * 2 ** attempt, 4000)
}

export function createQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: shouldRetry,
        retryDelay,
        // Twenty seconds, not zero and not five minutes. A front desk screen sits
        // open all day while someone else takes bookings on another; data that
        // never refetches goes quietly wrong, and data that refetches on every
        // focus change burns a free-tier instance's request budget on nothing.
        staleTime: 20_000,
        refetchOnWindowFocus: true,
        // A 401 that survived a rotation means the session is genuinely over. The
        // router reacts to that; a query should not keep hammering.
        throwOnError: false,
      },
      mutations: {
        retry: shouldRetry,
        retryDelay,
      },
    },
  })
}
