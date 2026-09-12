import { Link } from 'react-router-dom'
import { ExpiryChip } from './chips'
import { Panel, PanelHeader } from '@/components/ui/panel'
import { EmptyState, ErrorState, Skeleton } from '@/components/ui/states'
import { useToast } from '@/components/ui/toast-context'
import { useDismissAlert, useMembershipAlerts } from '@/hooks/use-alerts'
import { routes } from '@/lib/routes'

/**
 * Memberships needing attention (goal 10).
 *
 * Sorted with the already-expired first, which is what `days_remaining` being
 * negative is for — the interface does not re-derive the ordering, it reads it.
 *
 * Dismissing is scoped to the expiry date it was dismissed *for*, so the row
 * comes back the moment somebody renews and then lapses again. The copy says so:
 * "Hide until this date changes" rather than "Dismiss", because a front desk
 * needs to know whether they have silenced a reminder or lost it.
 */
export function AlertsPanel() {
  const alerts = useMembershipAlerts()
  const dismiss = useDismissAlert()
  const { notify } = useToast()

  return (
    <Panel>
      <PanelHeader
        label="Memberships needing attention"
        aside={alerts.data ? String(alerts.data.count) : undefined}
      />

      {alerts.isPending && <Skeleton rows={4} />}
      {alerts.error && <ErrorState error={alerts.error} onRetry={() => void alerts.refetch()} />}

      {alerts.data?.items.length === 0 && (
        <EmptyState title="Every membership is current">
          Anything expiring in the next {alerts.data.window_days} days will appear here.
        </EmptyState>
      )}

      {alerts.data && alerts.data.items.length > 0 && (
        <ul className="">
          {alerts.data.items.map((alert) => (
            <li
              key={alert.member_id}
              className="flex h-11 items-center justify-between gap-3 border-b border-hairline last:border-b-0"
            >
              <Link
                to={routes.memberSearch(alert.email)}
                className="min-w-0 text-14 underline-offset-2 hover:text-ink hover:underline"
              >
                {alert.full_name}
              </Link>
              <div className="flex shrink-0 items-center gap-3">
                <ExpiryChip daysRemaining={alert.days_remaining} />
                <button
                  type="button"
                  onClick={() =>
                    dismiss.mutate(alert.member_id, {
                      onSuccess: () =>
                        notify('Hidden', {
                          detail: `${alert.full_name} will reappear here if this expiry date changes.`,
                        }),
                    })
                  }
                  disabled={dismiss.isPending}
                  className="text-11 text-graphite underline-offset-2 hover:text-ink hover:underline disabled:text-mute"
                >
                  Hide
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}
