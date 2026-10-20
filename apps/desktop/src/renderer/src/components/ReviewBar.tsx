import { useState } from 'react'
import { LoaderCircle, Microscope, PauseCircle, X } from 'lucide-react'
import { useClaims, type ReviewScope } from '../store/claims'
import { buttonClass } from './Dialog'

function eta(seconds: number | null | undefined): string {
  if (!seconds) return ''
  if (seconds < 90) return `~${Math.max(1, Math.round(seconds / 10) * 10)} s`
  return `~${Math.round(seconds / 60)} min`
}

const SCOPES: { value: ReviewScope; label: string }[] = [
  { value: 'pending', label: 'ainda não revisadas' },
  { value: 'doubtful', label: 'só inconclusivas, fora de contexto ou com erro' },
  { value: 'all', label: 'todas (de novo)' }
]

/** Rechecagem com o modelo de qualidade depois da sessão (M6.1). */
export function ReviewBar(): React.JSX.Element | null {
  const review = useClaims((s) => s.review)
  const start = useClaims((s) => s.startReview)
  const cancel = useClaims((s) => s.cancelReview)
  const [scope, setScope] = useState<ReviewScope>('pending')
  const model = review?.model?.replace(/^\w+:/, '') ?? 'modelo de qualidade'
  const running = review && ['preparing', 'running', 'paused'].includes(review.state)

  if (running) {
    const pct = review.total ? (review.done / review.total) * 100 : 0
    return (
      <div
        className="mb-3 rounded-md border border-primary/30 bg-primary-soft/40 p-2.5 text-xs"
        data-testid="review-bar"
      >
        <div className="flex items-center gap-2 text-text">
          {review.state === 'paused' ? (
            <PauseCircle size={13} className="text-text-muted" />
          ) : (
            <LoaderCircle size={13} className="animate-spin text-primary" />
          )}
          <span className="font-medium" data-testid="review-progress">
            {review.state === 'preparing'
              ? 'Liberando memória para o modelo de qualidade…'
              : review.state === 'paused'
                ? `Revisão pausada durante a sessão ao vivo · ${review.done}/${review.total}`
                : `Rechecando com ${model} · ${review.done}/${review.total}`}
          </span>
          <span className="text-text-muted">{review.state === 'running' && eta(review.eta_s)}</span>
          <button
            type="button"
            onClick={() => void cancel()}
            className="ml-auto inline-flex items-center gap-1 text-text-muted hover:text-verdict-false"
            data-testid="cancel-review"
          >
            <X size={12} /> Cancelar
          </button>
        </div>
        <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-border/60">
          <div className="h-full bg-primary transition-[width]" style={{ width: `${pct}%` }} />
        </div>
      </div>
    )
  }

  return (
    <div className="mb-3 flex flex-wrap items-center gap-2 text-xs" data-testid="review-bar">
      <button
        type="button"
        className={`${buttonClass.secondary} inline-flex items-center gap-1.5`}
        onClick={() => void start(scope)}
        title="Depois da sessão, o rtfc tira a transcrição da memória e recheca com um modelo maior e mais preciso."
        data-testid="start-review"
      >
        <Microscope size={13} /> Rechecar com {model}
      </button>
      <select
        value={scope}
        onChange={(e) => setScope(e.target.value as ReviewScope)}
        aria-label="Quais afirmações rechecar"
        className="rounded border border-border bg-surface px-1.5 py-1 text-[11px] text-text"
      >
        {SCOPES.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
      {review?.state === 'done' && (
        <span className="text-text-muted" data-testid="review-done">
          {review.total ? `Revisão concluída (${review.done}/${review.total}).` : (review.message ?? '')}
        </span>
      )}
      {review?.state === 'cancelled' && <span className="text-text-muted">Revisão cancelada.</span>}
    </div>
  )
}
