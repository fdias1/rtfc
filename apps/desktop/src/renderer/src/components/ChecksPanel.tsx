import { useEffect, useRef } from 'react'
import { Clock, Copy, Hand, ListChecks, LoaderCircle, Settings, TriangleAlert, X } from 'lucide-react'
import type { ClaimData } from '@rtfc/protocol'
import { formatDuration } from '../lib/format'
import { useClaims, visibleClaims } from '../store/claims'
import { usePlayer } from '../store/player'
import { EmptyState } from './Panel'

const STATUS: Record<ClaimData['status'], { label: string; className: string }> = {
  queued: { label: 'Na fila', className: 'bg-border/60 text-text-muted' },
  checking: { label: 'Verificando…', className: 'bg-primary-soft text-primary-strong' },
  done: { label: 'Concluída', className: 'bg-primary-soft text-primary-strong' },
  cancelled: { label: 'Cancelada', className: 'bg-border/60 text-text-muted' },
  discarded: { label: 'Descartada', className: 'bg-border/60 text-text-muted' },
  error: { label: 'Erro', className: 'bg-verdict-false/10 text-verdict-false' }
}

/** Leva a transcrição até o trecho da afirmação (e toca, se houver player). */
export function revealClaim(claim: ClaimData, seekable: boolean): void {
  document
    .querySelector(`[data-seg="${claim.from_segment}"][data-word="${claim.from_word}"]`)
    ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  if (seekable) usePlayer.getState().seek(claim.start_ms)
}

function ClaimCard({ claim, focused, seekable }: { claim: ClaimData; focused: boolean; seekable: boolean }) {
  const focus = useClaims((s) => s.focus)
  const discard = useClaims((s) => s.discard)
  const ref = useRef<HTMLLIElement>(null)
  const status = STATUS[claim.status]

  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [focused])

  return (
    <li
      ref={ref}
      data-testid="claim-card"
      data-claim-id={claim.id}
      data-focused={focused || undefined}
      onClick={() => {
        focus(claim.id)
        revealClaim(claim, seekable)
      }}
      className={`group cursor-pointer rounded-md border p-3 transition-colors ${
        focused ? 'border-primary/50 bg-primary-soft/50' : 'border-border hover:border-primary/30'
      }`}
    >
      <div className="mb-1.5 flex items-center gap-2 text-[11px] text-text-muted">
        <span className="inline-flex items-center gap-1 font-mono">
          <Clock size={11} />
          {formatDuration(claim.start_ms)}
        </span>
        {claim.speaker && <span>· {claim.speaker}</span>}
        {claim.origin === 'manual' && (
          <span className="inline-flex items-center gap-0.5" title="Trecho escolhido por você">
            <Hand size={11} /> manual
          </span>
        )}
        {claim.dedup_of && (
          <span
            className="inline-flex items-center gap-0.5"
            title="Igual a uma afirmação anterior: o resultado será o mesmo"
          >
            <Copy size={11} /> repetida
          </span>
        )}
        <span className={`ml-auto rounded-full px-2 py-0.5 font-medium ${status.className}`} data-testid="claim-status">
          {status.label}
        </span>
        <button
          type="button"
          aria-label="Descartar afirmação"
          title="Descartar"
          data-testid="discard-claim"
          onClick={(e) => {
            e.stopPropagation()
            void discard(claim.id)
          }}
          className="text-text-muted opacity-0 transition-opacity group-hover:opacity-100 hover:text-verdict-false"
        >
          <X size={14} />
        </button>
      </div>
      <p className="text-sm leading-snug text-text" data-testid="claim-text">
        {claim.text}
      </p>
      {claim.source_text && claim.source_text !== claim.text && (
        <p className="mt-1.5 border-l-2 border-border pl-2 text-xs leading-snug text-text-muted">
          “{claim.source_text}”
        </p>
      )}
    </li>
  )
}

function ExtractorNotice({ onOpenSettings }: { onOpenSettings(): void }): React.JSX.Element | null {
  const extractor = useClaims((s) => s.extractor)
  if (!extractor) return null
  if (extractor.state === 'running') {
    return (
      <p className="mb-3 flex items-center gap-1.5 text-xs text-text-muted" data-testid="extractor-running">
        <LoaderCircle size={12} className="animate-spin" /> Procurando afirmações…
      </p>
    )
  }
  if (extractor.state !== 'error') return null
  return (
    <div
      role="alert"
      className="mb-3 rounded-md border border-verdict-context/40 bg-verdict-context/5 p-2.5 text-xs text-text"
    >
      <p className="flex items-start gap-1.5">
        <TriangleAlert size={13} className="mt-0.5 shrink-0 text-verdict-context" />
        <span>
          O extrator de afirmações falhou: <span className="text-text-muted">{extractor.message}</span>
        </span>
      </p>
      <button
        type="button"
        onClick={onOpenSettings}
        className="mt-1.5 inline-flex items-center gap-1 text-primary underline"
      >
        <Settings size={12} /> Ver configurações
      </button>
    </div>
  )
}

export function ChecksPanel({
  seekable,
  hasSession,
  onOpenSettings
}: {
  seekable: boolean
  hasSession: boolean
  onOpenSettings(): void
}): React.JSX.Element {
  const byId = useClaims((s) => s.byId)
  const focusedId = useClaims((s) => s.focusedId)
  const error = useClaims((s) => s.error)
  const claims = visibleClaims(byId)

  return (
    <div className="flex h-full flex-col">
      <ExtractorNotice onOpenSettings={onOpenSettings} />
      {error && (
        <p role="alert" className="mb-3 text-xs text-verdict-false">
          {error}
        </p>
      )}
      {claims.length === 0 ? (
        <EmptyState
          icon={<ListChecks size={32} strokeWidth={1.25} />}
          title="Nenhuma afirmação ainda"
          hint={
            hasSession
              ? 'As afirmações factuais detectadas aparecem aqui. Você também pode selecionar um trecho da transcrição e clicar em “Verificar trecho”.'
              : 'As afirmações factuais detectadas aparecem aqui com o veredicto e as fontes.'
          }
        />
      ) : (
        <ul className="flex flex-col gap-2" data-testid="claims-list">
          {claims.map((c) => (
            <ClaimCard key={c.id} claim={c} focused={c.id === focusedId} seekable={seekable} />
          ))}
        </ul>
      )}
    </div>
  )
}
