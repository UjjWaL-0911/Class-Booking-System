import { useState } from 'react'
import { downloadAttendanceCsv } from '@/api/bookings'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/toast-context'
import type { Session } from '@/api/types'

/**
 * Download one session's attendance as a CSV (goal 7).
 *
 * Shared rather than written twice, because the download is not a link. The
 * endpoint needs an `Authorization` header and an anchor sends none, so the
 * bytes come through the authenticated client and the save is triggered from a
 * blob — which is three things that can fail and one place they should be
 * handled.
 *
 * The pending label matters more than it looks: on a cold free-tier instance the
 * first request can take a few seconds, and a button that says nothing while it
 * waits is a button somebody presses again.
 */
export function ExportRegisterButton({
  session,
  size = 'md',
  variant = 'secondary',
  label = 'Export the register',
}: {
  session: Session
  size?: 'md' | 'sm'
  variant?: 'secondary' | 'quiet'
  label?: string
}) {
  const { notify } = useToast()
  const [busy, setBusy] = useState(false)

  return (
    <Button
      size={size}
      variant={variant}
      disabled={busy}
      onClick={() => {
        setBusy(true)
        downloadAttendanceCsv(session.id)
          .catch((error: unknown) =>
            notify(
              error instanceof ApiError ? error.message : 'Could not export the register.',
              { tone: 'bad' },
            ),
          )
          .finally(() => setBusy(false))
      }}
    >
      {busy ? 'Preparing' : label}
    </Button>
  )
}
