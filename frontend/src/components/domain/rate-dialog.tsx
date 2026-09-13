import { useEffect, useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextInput } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useSetRate } from '@/hooks/use-users'
import { formatMoney, toMinor, toTyped } from '@/lib/money'
import type { Teacher } from '@/api/types'

/**
 * What one person is paid to lead a session.
 *
 * The only thing about an account this app can edit, and the narrowness is the
 * point: a name change, an email change and a role change are three different
 * jobs with three different sets of rules, and a dialog whose fields half-work
 * would be worse than one that is honest about what it edits.
 *
 * **An empty box clears the rate, and that is not the same as typing 0.** "We
 * have not agreed a rate" is a thing somebody has to go and settle; "unpaid" is a
 * decision somebody made. The payroll report already refuses to add the first
 * into a total, so the form has to be able to express it.
 *
 * **Changing a rate changes what past reports say**, because payroll multiplies
 * sessions by the rate as it stands now. The dialog says so where somebody is
 * about to do it rather than leaving them to find out at the end of the month.
 * Dating rates is a second table and a temporal join; `decisions.md` records it
 * as the thing to build the first time a studio needs last month's figure back.
 */
export function RateDialog({
  person,
  onClose,
}: {
  person: Teacher | null
  onClose: () => void
}) {
  const { notify } = useToast()
  const setRate = useSetRate()
  const [typed, setTyped] = useState('')
  const [problem, setProblem] = useState<string | null>(null)

  useEffect(() => {
    if (!person) return
    setTyped(toTyped(person.session_rate_minor))
    setProblem(null)
    setRate.reset()
    // The mutation is recreated each render; depending on it would reset the box
    // under somebody mid-type.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [person])

  function save() {
    if (!person) return
    const minor = toMinor(typed)
    if (minor === undefined) {
      setProblem('Use digits and at most two decimal places, like 1200 or 1200.50.')
      return
    }
    setRate.mutate(
      { id: person.id, minor },
      {
        onSuccess: (saved) => {
          notify(saved.session_rate_minor === null ? 'Rate cleared' : 'Rate saved', {
            tone: 'good',
            detail:
              saved.session_rate_minor === null
                ? `${saved.full_name} has no rate set. Payroll will say so rather than count them as unpaid.`
                : `${saved.full_name} is paid ${formatMoney(saved.session_rate_minor)} a session.`,
          })
          onClose()
        },
      },
    )
  }

  const failed = setRate.error
    ? setRate.error instanceof ApiError
      ? setRate.error.message
      : 'Could not save that rate.'
    : null

  return (
    <Dialog
      open={person !== null}
      onOpenChange={(next) => !next && onClose()}
      title={person ? `${person.full_name}'s rate` : 'Rate'}
      description="What they are paid to lead one session. Past reports are recalculated from whatever it says now."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={save} disabled={setRate.isPending}>
            {setRate.isPending ? 'Saving' : 'Save the rate'}
          </Button>
        </>
      }
    >
      <Field
        label="Per session"
        hint="Leave it empty if no rate has been agreed — that is different from zero."
        error={problem}
      >
        {(id, describedBy) => (
          <TextInput
            id={id}
            autoFocus
            inputMode="decimal"
            placeholder="No rate set"
            aria-describedby={describedBy}
            invalid={problem !== null}
            value={typed}
            onChange={(event) => {
              setTyped(event.target.value)
              setProblem(null)
            }}
          />
        )}
      </Field>

      {failed && (
        <p role="alert" className="pt-4 text-14 text-bad-ink">
          {failed}
        </p>
      )}
    </Dialog>
  )
}
