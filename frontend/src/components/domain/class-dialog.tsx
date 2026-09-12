import { useEffect, useState } from 'react'
import { ApiError } from '@/api/errors'
import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { Field, TextArea, TextInput } from '@/components/ui/field'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { useCreateClass, useUpdateClass } from '@/hooks/use-classes'
import { firstProblem, LIMITS, maxLength, required, wholeNumber } from '@/lib/validation'
import type { StudioClass } from '@/api/types'

/**
 * Add or edit a class (goal 2).
 *
 * The one subtlety is `version`, sent on every edit. Two people with this dialog
 * open — a manager on a laptop, the desk on the shared screen — is an ordinary
 * Tuesday, and without the version the second save silently discards the first.
 * With it, the loser gets told, and the message says what to do: reopen and redo
 * the change. That is why a stale conflict here suggests closing rather than
 * offering a retry button, which would just save over the other person's work
 * one click later.
 */
export function ClassDialog({
  open,
  onOpenChange,
  studioClass,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  studioClass?: StudioClass | null
}) {
  const { notify } = useToast()
  const createClass = useCreateClass()
  const updateClass = useUpdateClass()

  const [title, setTitle] = useState('')
  const [discipline, setDiscipline] = useState('')
  const [description, setDescription] = useState('')
  const [duration, setDuration] = useState('60')
  const [capacity, setCapacity] = useState('12')

  const editing = studioClass != null
  const mutation = editing ? updateClass : createClass

  const form = useForm({
    title: firstProblem(required(title, 'a title'), maxLength(title, LIMITS.classTitle)),
    discipline: firstProblem(
      required(discipline, 'a discipline'),
      maxLength(discipline, LIMITS.discipline),
    ),
    description: maxLength(description, LIMITS.description),
    duration: wholeNumber(duration, LIMITS.duration),
    capacity: wholeNumber(capacity, LIMITS.capacity),
  })
  const { reset: resetForm } = form

  useEffect(() => {
    if (!open) return
    setTitle(studioClass?.title ?? '')
    setDiscipline(studioClass?.discipline ?? '')
    setDescription(studioClass?.description ?? '')
    setDuration(String(studioClass?.default_duration_min ?? 60))
    setCapacity(String(studioClass?.default_capacity ?? 12))
    resetForm()
  }, [open, studioClass, resetForm])

  function close() {
    onOpenChange(false)
    createClass.reset()
    updateClass.reset()
  }

  function submit() {
    const body = {
      title: title.trim(),
      discipline: discipline.trim().toLowerCase(),
      description: description.trim(),
      default_duration_min: Number(duration),
      default_capacity: Number(capacity),
    }

    if (editing) {
      updateClass.mutate(
        { id: studioClass.id, body: { ...body, version: studioClass.version } },
        {
          onSuccess: (saved) => {
            notify('Saved', { detail: `${saved.title} is up to date.` })
            close()
          },
        },
      )
    } else {
      createClass.mutate(body, {
        onSuccess: (saved) => {
          notify('Added', { tone: 'good', detail: `${saved.title} can now be put on the timetable.` })
          close()
        },
      })
    }
  }

  const error = mutation.error
  const stale = error instanceof ApiError && error.status === 409
  const message = error instanceof ApiError ? error.message : error ? 'Could not save that class.' : null

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => (next ? onOpenChange(true) : close())}
      title={editing ? 'Edit this class' : 'Add a class'}
      description={
        editing
          ? 'Changing the defaults does not change sessions already on the timetable.'
          : 'The length and capacity here are the defaults each session starts from.'
      }
      width="lg"
      footer={
        stale ? (
          <Button variant="primary" onClick={close}>
            Close and start again
          </Button>
        ) : (
          <>
            <Button onClick={close}>Cancel</Button>
            <Button
              variant="primary"
              onClick={() => form.submit(submit)}
              disabled={mutation.isPending}
            >
              {mutation.isPending ? 'Saving' : editing ? 'Save changes' : 'Add the class'}
            </Button>
          </>
        )
      }
    >
      <div className="flex flex-col gap-5">
        <Field label="Title" error={form.error('title')}>
          {(id, describedBy) => (
            <TextInput
              id={id}
              aria-describedby={describedBy}
              autoFocus
              invalid={form.error('title') !== null}
              value={title}
              placeholder="Vinyasa Flow"
              onChange={(event) => setTitle(event.target.value)}
              onBlur={() => form.touch('title')}
            />
          )}
        </Field>

        <Field
          label="Discipline"
          hint="Groups the class and gives it its colour on the timetable — yoga, cycling, dance, pilates."
          error={form.error('discipline')}
        >
          {(id, describedBy) => (
            <TextInput
              id={id}
              aria-describedby={describedBy}
              invalid={form.error('discipline') !== null}
              value={discipline}
              placeholder="yoga"
              onChange={(event) => setDiscipline(event.target.value)}
              onBlur={() => form.touch('discipline')}
            />
          )}
        </Field>

        <Field
          label="Description"
          hint="What a member would want to know before coming."
          error={form.error('description')}
        >
          {(id, describedBy) => (
            <TextArea
              id={id}
              aria-describedby={describedBy}
              value={description}
              rows={3}
              onChange={(event) => setDescription(event.target.value)}
              onBlur={() => form.touch('description')}
            />
          )}
        </Field>

        <div className="grid grid-cols-2 gap-4">
          <Field label="Usual length" hint="Minutes" error={form.error('duration')}>
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="number"
                inputMode="numeric"
                aria-describedby={describedBy}
                invalid={form.error('duration') !== null}
                value={duration}
                onChange={(event) => setDuration(event.target.value)}
                onBlur={() => form.touch('duration')}
              />
            )}
          </Field>
          <Field
            label="Usual capacity"
            hint="How many people fit in the room."
            error={form.error('capacity')}
          >
            {(id, describedBy) => (
              <TextInput
                id={id}
                type="number"
                inputMode="numeric"
                aria-describedby={describedBy}
                invalid={form.error('capacity') !== null}
                value={capacity}
                onChange={(event) => setCapacity(event.target.value)}
                onBlur={() => form.touch('capacity')}
              />
            )}
          </Field>
        </div>

        {form.blocked && (
          <p role="alert" className="text-14 text-bad-ink">
            Nothing was saved. Check the fields marked above.
          </p>
        )}

        {message && (
          <p role="alert" className="text-14 text-bad-ink">
            {message}
            {stale && ' Your changes were not saved.'}
          </p>
        )}
      </div>
    </Dialog>
  )
}
