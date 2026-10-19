import type { ReactNode } from 'react'

interface PanelProps {
  title: string
  children: ReactNode
  className?: string
}

export function Panel({ title, children, className = '' }: PanelProps): React.JSX.Element {
  return (
    <section className={`flex min-h-0 flex-col rounded-card border border-border bg-surface ${className}`}>
      <h2 className="border-b border-border px-4 py-3 text-xs font-semibold tracking-wide text-text-muted uppercase">
        {title}
      </h2>
      <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
    </section>
  )
}

export function EmptyState({ icon, title, hint }: { icon: ReactNode; title: string; hint: string }): React.JSX.Element {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-text-muted">
      <div className="text-primary/60">{icon}</div>
      <p className="text-sm font-medium text-text">{title}</p>
      <p className="max-w-64 text-xs leading-relaxed">{hint}</p>
    </div>
  )
}
