/**
 * Errors, as the backend actually sends them.
 *
 * There are two shapes on the wire and the difference matters. The domain sends
 * `{code, message, details}` and the message is written to be read by a person —
 * goal 4 requires that a rejected booking says why, and that sentence is composed
 * where the rule lives, so the interface must show it rather than substitute a
 * friendlier guess. FastAPI's own request validation sends `{detail: [...]}`,
 * which is machine-shaped and never fit to display; that one gets a written
 * fallback.
 */

import type { BookingStatus } from './types'

/** The domain error codes this interface reacts to differently. */
export type ApiErrorCode =
  | 'not_found'
  | 'permission_denied'
  | 'authentication_failed'
  | 'rule_violation'
  | 'illegal_transition'
  | 'conflict'
  | 'lock_timeout'
  | 'domain_error'
  | 'validation_error'
  | 'network_error'

interface DomainErrorBody {
  code: string
  message: string
  details?: Record<string, unknown>
}

interface ValidationErrorBody {
  detail: { loc: (string | number)[]; msg: string; type: string }[]
}

export class ApiError extends Error {
  readonly status: number
  readonly code: ApiErrorCode
  readonly details: Record<string, unknown>
  readonly retryAfterSeconds: number | null

  constructor(
    status: number,
    code: ApiErrorCode,
    message: string,
    details: Record<string, unknown> = {},
    retryAfterSeconds: number | null = null,
  ) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
    this.retryAfterSeconds = retryAfterSeconds
  }

  /** True when trying the same thing again is a reasonable response. */
  get isRetryable(): boolean {
    return this.code === 'lock_timeout' || this.code === 'network_error'
  }

  /** A stale `version` — the row changed under an open edit form. */
  get isStaleWrite(): boolean {
    return this.status === 409 && this.details['expected'] !== undefined
  }

  /** Set on an illegal transition, so the interface can name the current state. */
  get currentStatus(): BookingStatus | null {
    const value = this.details['current']
    return typeof value === 'string' ? (value as BookingStatus) : null
  }
}

function isDomainBody(body: unknown): body is DomainErrorBody {
  return (
    typeof body === 'object' &&
    body !== null &&
    typeof (body as DomainErrorBody).code === 'string' &&
    typeof (body as DomainErrorBody).message === 'string'
  )
}

function isValidationBody(body: unknown): body is ValidationErrorBody {
  return (
    typeof body === 'object' && body !== null && Array.isArray((body as ValidationErrorBody).detail)
  )
}

/** Turn a failed response into an ApiError, reading the body where there is one. */
export async function toApiError(response: Response): Promise<ApiError> {
  const retryAfter = Number(response.headers.get('retry-after'))
  const retryAfterSeconds = Number.isFinite(retryAfter) && retryAfter > 0 ? retryAfter : null

  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // A 502 from the platform, or a 500 that never reached the handlers, has no
    // JSON body. Fall through to the status-based message below.
  }

  if (isDomainBody(body)) {
    return new ApiError(
      response.status,
      body.code as ApiErrorCode,
      body.message,
      body.details ?? {},
      retryAfterSeconds,
    )
  }

  if (isValidationBody(body)) {
    // Deliberately not shown to the user as-is: "body.membership_expiry: Input
    // should be a valid date" is a developer's sentence. The field errors are
    // kept in details so a form can highlight the right input.
    const fields = Object.fromEntries(
      body.detail.map((item) => [item.loc.filter((part) => part !== 'body').join('.'), item.msg]),
    )
    return new ApiError(
      response.status,
      'validation_error',
      'Some of those details were not accepted. Check the highlighted fields.',
      { fields },
      retryAfterSeconds,
    )
  }

  return new ApiError(
    response.status,
    'domain_error',
    response.status >= 500
      ? 'Something went wrong at our end. Try again in a moment.'
      : `The request was rejected (${response.status}).`,
    {},
    retryAfterSeconds,
  )
}

/** The browser could not reach the server at all. Distinct from any HTTP status. */
export function networkError(cause: unknown): ApiError {
  return new ApiError(
    0,
    'network_error',
    'Could not reach the server. Check your connection and try again.',
    { cause: String(cause) },
  )
}
