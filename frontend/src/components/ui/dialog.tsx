import * as RadixDialog from '@radix-ui/react-dialog'
import type { ReactNode } from 'react'
import { cn } from '@/lib/cn'

/**
 * Radix does the parts that are easy to get wrong and invisible when you do:
 * focus trapping, returning focus to whatever opened it, `aria-modal`, Escape,
 * and locking the scroll behind it. Those are the only components in this app
 * that are not hand-built, and the reason is that a hand-rolled focus trap is a
 * bug that only shows up for somebody using a keyboard.
 *
 * The styling is entirely ours. This is the one surface with a shadow, because it
 * is the one surface genuinely in front of the page.
 */
interface DialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  /** One sentence saying what this dialog will do. Read out with the title. */
  description?: string
  children: ReactNode
  footer?: ReactNode
  width?: 'md' | 'lg' | 'xl'
}

const WIDTHS = {
  md: 'max-w-[460px]',
  lg: 'max-w-[640px]',
  // Wide enough for the session picker's rows to hold a time, a class, a room and
  // an occupancy mark without any of them truncating.
  xl: 'max-w-[820px]',
} as const

export function Dialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  width = 'md',
}: DialogProps) {
  return (
    <RadixDialog.Root open={open} onOpenChange={onOpenChange}>
      <RadixDialog.Portal>
        <RadixDialog.Overlay className="fixed inset-0 z-40 bg-scrim backdrop-blur-[1px]" />
        <RadixDialog.Content
          className={cn(
            'fixed left-1/2 top-1/2 z-50 flex max-h-[85vh] w-[calc(100vw-32px)] -translate-x-1/2 -translate-y-1/2',
            'flex-col overflow-hidden rounded-md border border-rule bg-card shadow-overlay',
            WIDTHS[width],
          )}
        >
          <div className="flex flex-col gap-1 border-b border-rule px-6 pb-4 pt-5">
            <RadixDialog.Title className="text-16 font-semibold tracking-[-0.01em]">
              {title}
            </RadixDialog.Title>
            {description && (
              <RadixDialog.Description className="max-w-[58ch] text-14 text-graphite">
                {description}
              </RadixDialog.Description>
            )}
          </div>

          <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>

          {footer && (
            <div className="flex items-center justify-end gap-2 border-t border-rule px-6 py-4">
              {footer}
            </div>
          )}
        </RadixDialog.Content>
      </RadixDialog.Portal>
    </RadixDialog.Root>
  )
}

export const DialogClose = RadixDialog.Close
