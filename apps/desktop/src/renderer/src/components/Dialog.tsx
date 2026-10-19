import { useEffect, type ReactNode } from 'react'
import { X } from 'lucide-react'

interface DialogProps {
  title: string
  onClose(): void
  children: ReactNode
  footer?: ReactNode
  width?: string
}

export function Dialog({ title, onClose, children, footer, width = 'max-w-lg' }: DialogProps): React.JSX.Element {
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-20 flex items-center justify-center bg-text/25 p-6" onMouseDown={onClose}>
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className={`flex max-h-full w-full ${width} flex-col rounded-card border border-border bg-surface shadow-xl`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border px-5 py-3">
          <h2 className="text-sm font-semibold text-text">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Fechar" className="text-text-muted hover:text-text">
            <X size={16} />
          </button>
        </div>
        <div className="min-h-0 overflow-y-auto px-5 py-4 text-sm text-text">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-border px-5 py-3">{footer}</div>}
      </div>
    </div>
  )
}

export const buttonClass = {
  primary: 'rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-white hover:bg-primary-strong',
  secondary: 'rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-text hover:bg-primary-soft',
  danger: 'rounded-md bg-verdict-false px-3 py-1.5 text-xs font-medium text-white hover:opacity-90'
}
