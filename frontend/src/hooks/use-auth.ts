import { useSyncExternalStore } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { signIn, signOut } from '@/api/auth'
import { getSessionState, subscribe } from '@/api/token-store'
import type { SessionState } from '@/api/token-store'
import { routes } from '@/lib/routes'
import type { User } from '@/api/types'

/**
 * The signed-in session.
 *
 * `useSyncExternalStore` rather than a context holding state, because the token
 * store is written from outside React — the fetch client rotates the session on a
 * 401, and that happens inside a promise nobody is rendering. A context would
 * need something to call `setState` for it, and there is nothing there to do it.
 */
export function useSession(): SessionState {
  return useSyncExternalStore(subscribe, getSessionState)
}

/**
 * The signed-in user, where the route has already established there is one.
 *
 * Throws rather than returning null. Inside a protected route the alternative is
 * a null check in every component that wants a name or a role, and one of them
 * eventually gets it wrong.
 */
export function useCurrentUser(): User {
  const { user } = useSession()
  if (user === null) {
    throw new Error('useCurrentUser was called outside a signed-in route.')
  }
  return user
}

export function useIsStaff(): boolean {
  return useSession().user?.role === 'staff'
}

/**
 * Whether this session belongs to a member rather than to the studio.
 *
 * Used to route, never to authorize: every member endpoint resolves the member
 * from the credential and every studio endpoint refuses this role outright, so
 * being wrong here makes the app land somebody on the wrong screen rather than
 * showing them a row they should not see.
 */
export function useIsMember(): boolean {
  return useSession().user?.role === 'member'
}

/** Where this person's app starts. Members and studio staff do not share a home. */
export function homeFor(role: User['role'] | undefined): string {
  return role === 'member' ? routes.myBookings : routes.today
}

export function useSignIn() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      signIn(email, password),
    onSuccess: () => {
      // The previous occupant of this browser tab may have been an instructor
      // with a narrower view of the studio. Anything cached under their session
      // is not this person's data.
      queryClient.clear()
    },
  })
}

export function useSignOut() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: signOut,
    onSettled: () => {
      queryClient.clear()
    },
  })
}
