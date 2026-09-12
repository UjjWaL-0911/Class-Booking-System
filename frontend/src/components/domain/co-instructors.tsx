import { useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Select } from '@/components/ui/field'
import { Panel, PanelHeader } from '@/components/ui/panel'
import { useToast } from '@/components/ui/toast-context'
import { useAddCoInstructor, useRemoveCoInstructor, useTeachers } from '@/hooks/use-sessions'
import type { Session } from '@/api/types'

/**
 * Co-instructors (goal 5).
 *
 * Only staff may add or remove one, and the panel explains what adding somebody
 * actually does: it gives them sight of the session in their own timetable. That
 * is the substance of goal 5 — the visibility, not the label — and it is not
 * obvious from a list of names.
 *
 * The primary instructor is deliberately absent from the dropdown. One person
 * cannot be both, and offering the choice only to refuse it is worse than not
 * offering it.
 */
export function CoInstructors({ session }: { session: Session }) {
  const { notify } = useToast()
  const teachers = useTeachers()
  const add = useAddCoInstructor()
  const remove = useRemoveCoInstructor()
  const [choice, setChoice] = useState('')

  const taken = new Set([session.primary_instructor.id, ...session.co_instructors.map((p) => p.id)])
  const available = (teachers.data ?? []).filter((person) => !taken.has(person.id))
  const error = add.error ?? remove.error

  return (
    <Panel>
      <PanelHeader
        label="Teaching this class"
        aside="A co-instructor sees this session in their own timetable"
      />

      <div className="flex flex-col gap-3 pb-4">
        <div className="flex items-center justify-between gap-4">
          <div className="flex flex-col">
            <span className="text-14 font-medium">{session.primary_instructor.full_name}</span>
            <span className="text-11 text-graphite">Leading the class</span>
          </div>
        </div>

        {session.co_instructors.map((person) => (
          <div key={person.id} className="flex items-center justify-between gap-4">
            <div className="flex flex-col">
              <span className="text-14">{person.full_name}</span>
              <span className="text-11 text-graphite">Helping out</span>
            </div>
            <button
              type="button"
              disabled={remove.isPending}
              onClick={() =>
                remove.mutate(
                  { sessionId: session.id, userId: person.id },
                  {
                    onSuccess: () =>
                      notify('Removed', {
                        detail: `${person.full_name} no longer sees this class in their timetable.`,
                      }),
                  },
                )
              }
              className="text-12 text-graphite underline-offset-2 hover:text-bad-ink hover:underline disabled:text-mute"
            >
              Remove
            </button>
          </div>
        ))}
      </div>

      {available.length > 0 && (
        <div className="flex items-end gap-2 border-t border-hairline pt-4">
          <Select
            aria-label="Add a co-instructor"
            value={choice}
            onChange={(event) => setChoice(event.target.value)}
            className="flex-1"
          >
            <option value="">Add someone else</option>
            {available.map((person) => (
              <option key={person.id} value={person.id}>
                {person.full_name}
              </option>
            ))}
          </Select>
          <Button
            disabled={choice === '' || add.isPending}
            onClick={() => {
              const person = available.find((item) => item.id === choice)
              add.mutate(
                { sessionId: session.id, userId: choice },
                {
                  onSuccess: () => {
                    notify('Added', {
                      detail: `${person?.full_name ?? 'They'} can now see this class in their timetable.`,
                    })
                    setChoice('')
                  },
                },
              )
            }}
          >
            {add.isPending ? 'Adding' : 'Add'}
          </Button>
        </div>
      )}

      {error && (
        <p role="alert" className="pt-3 text-14 text-bad-ink">
          {error instanceof ApiError ? error.message : 'Could not change who is teaching.'}
        </p>
      )}
    </Panel>
  )
}
