import { CircleCheck, LoaderCircle, TriangleAlert } from 'lucide-react'
import { summarize, useConnection } from '../store/connection'

const LABELS = {
  connected: 'Backend conectado',
  connecting: 'Conectando ao backend…',
  failed: 'Backend indisponível'
} as const

export function ConnectionBadge(): React.JSX.Element {
  const sidecar = useConnection((s) => s.sidecar)
  const socket = useConnection((s) => s.socket)
  const latency = useConnection((s) => s.latencyMs)
  const summary = summarize(sidecar, socket)

  const tone =
    summary === 'connected'
      ? 'bg-primary-soft text-primary-strong'
      : summary === 'failed'
        ? 'bg-verdict-false/10 text-verdict-false'
        : 'bg-border/60 text-text-muted'

  return (
    <div className="flex items-center gap-2">
      <span
        data-testid="connection-status"
        data-state={summary}
        title={sidecar.lastError}
        className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${tone}`}
      >
        {summary === 'connected' && <CircleCheck size={14} strokeWidth={1.75} />}
        {summary === 'connecting' && <LoaderCircle size={14} strokeWidth={1.75} className="animate-spin" />}
        {summary === 'failed' && <TriangleAlert size={14} strokeWidth={1.75} />}
        {LABELS[summary]}
        {summary === 'connected' && latency !== undefined && (
          <span className="font-mono text-[11px] opacity-70">{latency} ms</span>
        )}
      </span>
      {summary === 'failed' && (
        <button
          type="button"
          onClick={() => void window.rtfc.restartSidecar()}
          className="rounded-md border border-border bg-surface px-2 py-1 text-xs text-primary hover:bg-primary-soft"
        >
          Tentar de novo
        </button>
      )}
    </div>
  )
}
