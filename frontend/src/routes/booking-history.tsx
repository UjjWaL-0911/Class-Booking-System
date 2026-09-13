import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ApiError } from '@/api/errors'
import { BookingTimeline } from '@/components/domain/booking-timeline'
import { ExpiryChip, StatusChip } from '@/components/domain/chips'
import { Button } from '@/components/ui/button'
import { Field, TextArea } from '@/components/ui/field'
import { Panel, PanelHeader } from '@/components/ui/panel'
import { BootScreen, ErrorState } from '@/components/ui/states'
import { useToast } from '@/components/ui/toast-context'
import { useForm } from '@/hooks/use-form'
import { useAddBookingNote, useBookingTimeline } from '@/hooks/use-bookings'
import { useStudio } from '@/studio/studio-context'
import { Page, PageHeader } from '@/layout/app-shell'
import { daysBetween, formatInstant } from '@/lib/dates'
import { firstProblem, LIMITS, maxLength, required } from '@/lib/validation'
import { routes } from '@/lib/routes'

/**
 * One booking's whole history (goal 9).
 *
 * The screen is arranged as a record rather than as a detail page: the timeline
 * is the main column, and the facts beside it are the ones you would want while
 * reading it — who the member is, whether their membership was valid, when the
 * booking was taken.
 *
 * The note box is at the bottom of the record, not in a dialog, and its label
 * says what adding one does. There is no edit affordance anywhere on this page
 * because there is no edit: the table refuses updates and deletes, and a
 * correction is a new entry that says what was wrong.
 */
export function BookingHistoryPage() {
  const { bookingId = '' } = useParams()
  const { timeZone, today } = useStudio()
  const { notify } = useToast()

  const booking = useBookingTimeline(bookingId)
  const addNote = useAddBookingNote()
  const [note, setNote] = useState('')

  const form = useForm({
    note: firstProblem(
      required(note, 'what you want recorded'),
      maxLength(note, LIMITS.bookingNote),
    ),
  })

  if (booking.isPending) return <BootScreen>Opening the record</BootScreen>
  if (booking.error) {
    return (
      <Page>
        <ErrorState error={booking.error} onRetry={() => void booking.refetch()} />
        <Link to={routes.bookings} className="text-14 text-graphite hover:text-ink hover:underline">
          Back to bookings
        </Link>
      </Page>
    )
  }

  const data = booking.data
  const daysRemaining = daysBetween(today, data.member.membership_expiry)

  return (
    <Page>
      <PageHeader
        back={
          <Link
            to={routes.bookings}
            className="inline-flex items-center gap-1.5 self-start text-12 text-graphite hover:text-ink hover:underline"
          >
            <svg width="11" height="11" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polyline points="7.5,2 3.5,6 7.5,10" />
            </svg>
            Bookings
          </Link>
        }
        title={data.member.full_name}
        subtitle={
          <Link
            to={routes.session(data.session_id)}
            className="text-14 hover:text-ink hover:underline"
          >
            Open the class this booking is for
          </Link>
        }
        actions={
          <StatusChip
            status={data.status}
            position={data.waitlist_position}
            className="mt-1"
          />
        }
      />

      <div className="grid grid-cols-1 items-start gap-8 xl:grid-cols-[minmax(0,1fr)_320px]">
        <Panel className="min-w-0 px-6 pb-2 pt-0">
          <PanelHeader
            label="Everything that happened to this booking"
            aside={`${data.events.length} ${data.events.length === 1 ? 'entry' : 'entries'}`}
            className="border-b border-rule px-0"
          />

          <div className="pt-5">
            <BookingTimeline events={data.events} />
          </div>

          <div className="flex items-center gap-2.5 border-t border-rule py-3.5">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="var(--color-graphite)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="7" width="10" height="7" rx="1.5" />
              <path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2" />
            </svg>
            <p className="text-14 text-graphite">
              This history cannot be changed. Entries are only ever added.
            </p>
          </div>
        </Panel>

        <div className="flex flex-col gap-6">
          <Panel padded className="flex flex-col gap-3.5">
            <span className="text-12 font-medium text-graphite">The member</span>
            <div className="flex flex-col">
              <span className="text-16 font-semibold tracking-[-0.01em]">
                {data.member.full_name}
              </span>
              <a
                href={`mailto:${data.member.email}`}
                className="text-12 text-graphite hover:text-ink hover:underline"
              >
                {data.member.email}
              </a>
            </div>
            <div className="flex items-center gap-3">
              <ExpiryChip daysRemaining={daysRemaining} />
              <Link
                to={routes.memberSearch(data.member.email)}
                className="text-12 text-graphite hover:text-ink hover:underline"
              >
                Open their record
              </Link>
            </div>
          </Panel>

          <Panel padded className="flex flex-col gap-3">
            <span className="text-12 font-medium text-graphite">This booking</span>
            <Fact label="Taken">{formatInstant(data.booked_at, timeZone)}</Fact>
            {data.cancelled_at && (
              <Fact label="Cancelled">{formatInstant(data.cancelled_at, timeZone)}</Fact>
            )}
            {data.settled_at && (
              <Fact label="Settled">{formatInstant(data.settled_at, timeZone)}</Fact>
            )}
            <div className="flex items-center justify-between gap-4 text-14">
              <span className="text-graphite">Now</span>
              <StatusChip status={data.status} position={data.waitlist_position} />
            </div>
            {/* Spelled out as a sentence as well as a chip. This is the page open
                while somebody is being told the answer on the phone, and "2nd"
                beside a word is easy to misread as part of the status. */}
            {data.waitlist_position !== null && (
              <p className="text-12 leading-[1.5] text-graphite">
                {data.waitlist_position === 1
                  ? 'Next in line — the first seat to free up is theirs.'
                  : `${data.waitlist_position - 1} ${data.waitlist_position === 2 ? 'person is' : 'people are'} ahead of them.`}
              </p>
            )}
          </Panel>

          <Panel padded className="flex flex-col gap-3">
            <Field
              label="Add a note"
              hint="A correction is a new entry, never an edit. Say what was wrong."
              error={form.error('note')}
            >
              {(id, describedBy) => (
                <TextArea
                  id={id}
                  aria-describedby={describedBy}
                  invalid={form.error('note') !== null}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  onBlur={() => form.touch('note')}
                  placeholder="What happened, and who said so"
                />
              )}
            </Field>
            <Button
              variant="primary"
              className="self-start"
              disabled={addNote.isPending}
              onClick={() =>
                form.submit(() =>
                  addNote.mutate(
                  { bookingId: data.id, note: note.trim() },
                  {
                    onSuccess: () => {
                      notify('Note added', { detail: 'It is now part of this booking’s history.' })
                      setNote('')
                      },
                    },
                  ),
                )
              }
            >
              {addNote.isPending ? 'Adding' : 'Add the note'}
            </Button>
            {addNote.error && (
              <p role="alert" className="text-14 text-bad-ink">
                {addNote.error instanceof ApiError
                  ? addNote.error.message
                  : 'Could not add that note.'}
              </p>
            )}
          </Panel>
        </div>
      </div>
    </Page>
  )
}

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 text-14">
      <span className="text-graphite">{label}</span>
      <span>{children}</span>
    </div>
  )
}
