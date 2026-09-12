/**
 * The wire format, mirrored from the backend's Pydantic models.
 *
 * Written by hand rather than generated. That is a deliberate trade: a generator
 * would keep these in step automatically, but it would also import forty endpoint
 * signatures the interface never calls and bury the distinctions that actually
 * matter here — which are documented in the modules below, beside the fields they
 * apply to.
 *
 * This file is only the front door. Everything lives under `model/`, split the
 * way the API is: `common` for the scalars every module needs, then one module
 * per area. Importing from `@/api/types` gets all of it, so nothing downstream
 * needs to know which file a type came from.
 */

export type * from './model/common'
export type * from './model/people'
export type * from './model/catalogue'
export type * from './model/schedule'
export type * from './model/booking'
export type * from './model/insights'
