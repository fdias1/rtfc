import { useEffect, useRef } from 'react'
import {
  Ban,
  Clock,
  Copy,
  ExternalLink,
  Hand,
  ListChecks,
  LoaderCircle,
  RotateCcw,
  Settings,
  TriangleAlert,
  X
} from 'lucide-react'
import type { CheckData, ClaimData } from '@rtfc/protocol'
import { formatDuration } from '../lib/format'
import {
  STAGE_LABEL,
  STANCE_LABEL,
  TIER_LABEL,
  VERDICT,
  confidenceLabel,
  isPending,
  type Verdict
} from '../lib/verdict'
import { useClaims, visibleClaims, type ClaimFilters } from '../store/claims'
import { usePlayer } from '../store/player'
import { EmptyState } from './Panel'

/** Leva a transcrição até o trecho da afirmação (e toca, se houver player). */
export function revealClaim(claim: ClaimData, seekable: boolean): void {
  document
    .querySelector(`[data-seg="${claim.from_segment}"][data-word="${claim.from_word}"]`)
    ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  if (seekable) usePlayer.getState().seek(claim.start_ms)
}

function StatusChip({ claim }: { claim: ClaimData }): React.JSX.Element {
  if (claim.status === 'done' && claim.check) {
    const v = VERDICT[claim.check.verdict]
    const Icon = v.icon
    return (
      <span
        className={`ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-semibold ${v.bg} ${v.text}`}
        data-testid="claim-status"
        data-verdict={claim.check.verdict}
      >
        <Icon size={12} strokeWidth={2.25} /> {v.label}
      </span>
    )
  }
  const labels: Record<ClaimData['status'], string> = {
    queued: 'Na fila',
    checking: claim.stage ? STAGE_LABEL[claim.stage] : 'Verificando…',
    done: 'Concluída',
    cancelled: 'Cancelada',
    discarded: 'Descartada',
    error: 'Erro'
  }
  const tone =
    claim.status === 'error'
      ? 'bg-verdict-false/10 text-verdict-false'
      : claim.status === 'checking'
        ? 'bg-primary-soft text-primary-strong'
        : 'bg-border/60 text-text-muted'
  return (
    <span
      className={`ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-medium ${tone}`}
      data-testid="claim-status"
      data-status={claim.status}
    >
      {claim.status === 'checking' && <LoaderCircle size={11} className="animate-spin" />}
      {labels[claim.status]}
    </span>
  )
}

function CheckResult({ check }: { check: CheckData }): React.JSX.Element {
  const v = VERDICT[check.verdict]
  return (
    <div className="mt-2 flex flex-col gap-2" data-testid="check-result" data-checked-at={check.checked_at}>
      <div className="flex items-center gap-2 text-[11px] text-text-muted">
        <span>Confiança {confidenceLabel(check.confidence)}</span>
        <span className="h-1.5 w-20 overflow-hidden rounded-full bg-border/60" aria-hidden>
          <span className={`block h-full ${v.bar}`} style={{ width: `${check.confidence * 100}%` }} />
        </span>
      </div>
      <p className="text-xs leading-relaxed text-text" data-testid="check-justification">
        {check.justification}
      </p>
      {check.sources.length > 0 && (
        <ul className="flex flex-col gap-1.5" data-testid="check-sources">
          {check.sources.map((s, i) => (
            <li key={i} className="rounded border border-border/70 bg-bg/60 px-2 py-1.5 text-[11px]">
              <a
                href={s.url}
                target="_blank"
                rel="noreferrer"
                onClick={(e) => e.stopPropagation()}
                className="flex items-center gap-1 font-medium text-primary hover:underline"
                title={s.url}
              >
                <span className="truncate">{s.title || s.domain}</span>
                <ExternalLink size={11} className="shrink-0" />
              </a>
              <span className="flex flex-wrap items-center gap-x-1.5 text-text-muted">
                <span>{s.domain}</span>·<span>{TIER_LABEL[s.tier] ?? s.tier}</span>·
                <span
                  className={
                    s.stance === 'refuta' ? 'text-verdict-false' : s.stance === 'apoia' ? 'text-verdict-true' : ''
                  }
                >
                  {STANCE_LABEL[s.stance] ?? s.stance}
                </span>
              </span>
              {s.quote && <span className="mt-0.5 block text-text">“{s.quote}”</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function ClaimCard({ claim, focused, seekable }: { claim: ClaimData; focused: boolean; seekable: boolean }) {
  const focus = useClaims((s) => s.focus)
  const discard = useClaims((s) => s.discard)
  const cancel = useClaims((s) => s.cancel)
  const retry = useClaims((s) => s.retry)
  const ref = useRef<HTMLLIElement>(null)
  const pending = isPending(claim)
  const verdict = claim.status === 'done' ? claim.check?.verdict : undefined

  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [focused])

  const action = (label: string, icon: React.ReactNode, onClick: () => void, testId: string) => (
    <button
      type="button"
      aria-label={label}
      title={label}
      data-testid={testId}
      onClick={(e) => {
        e.stopPropagation()
        onClick()
      }}
      className="text-text-muted hover:text-primary"
    >
      {icon}
    </button>
  )

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
      className={`group cursor-pointer rounded-md border border-l-4 p-3 transition-colors ${
        verdict ? VERDICT[verdict].border : 'border-l-border'
      } ${focused ? 'border-primary/50 bg-primary-soft/40' : 'border-border hover:border-primary/30'}`}
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
            title="Igual a uma afirmação anterior: o resultado é o mesmo"
          >
            <Copy size={11} /> repetida
          </span>
        )}
        <StatusChip claim={claim} />
        <span className="flex gap-1.5 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
          {pending && action('Cancelar checagem', <Ban size={13} />, () => void cancel(claim.id), 'cancel-check')}
          {!pending && action('Checar de novo', <RotateCcw size={13} />, () => void retry(claim.id), 'retry-check')}
          {action('Descartar', <X size={14} />, () => void discard(claim.id), 'discard-claim')}
        </span>
      </div>
      <p className="text-sm leading-snug text-text" data-testid="claim-text">
        {claim.text}
      </p>
      {claim.context && (
        <p className="mt-1 text-[11px] leading-snug text-text-muted" data-testid="claim-context">
          {claim.context}
        </p>
      )}
      {claim.source_text && claim.source_text !== claim.text && (
        <p className="mt-1.5 border-l-2 border-border pl-2 text-xs leading-snug text-text-muted">
          “{claim.source_text}”
        </p>
      )}
      {claim.status === 'error' && claim.error && (
        <p className="mt-1.5 flex items-start gap-1 text-xs text-verdict-false">
          <TriangleAlert size={12} className="mt-0.5 shrink-0" /> {claim.error}
        </p>
      )}
      {claim.status === 'done' && claim.check && <CheckResult check={claim.check} />}
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

const VERDICT_ORDER: Verdict[] = ['falso', 'fora_de_contexto', 'verdadeiro', 'inconclusivo']

function applyFilters(claims: ClaimData[], f: ClaimFilters): ClaimData[] {
  return claims.filter(
    (c) =>
      (!f.pendingOnly || isPending(c)) &&
      (f.speaker === 'all' || c.speaker === f.speaker) &&
      (f.verdict === 'all' || (c.status === 'done' && c.check?.verdict === f.verdict))
  )
}

function FilterBar({ claims }: { claims: ClaimData[] }): React.JSX.Element | null {
  const filters = useClaims((s) => s.filters)
  const setFilters = useClaims((s) => s.setFilters)
  if (claims.length === 0) return null
  const counts = Object.fromEntries(
    VERDICT_ORDER.map((v) => [v, claims.filter((c) => c.status === 'done' && c.check?.verdict === v).length])
  ) as Record<Verdict, number>
  const pending = claims.filter(isPending).length
  const speakers = [...new Set(claims.map((c) => c.speaker).filter(Boolean))] as string[]

  const chip = (active: boolean): string =>
    `inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] transition-colors ${
      active
        ? 'border-primary bg-primary-soft text-primary-strong'
        : 'border-border text-text-muted hover:border-primary/40'
    }`

  return (
    <div className="mb-3 flex flex-wrap items-center gap-1.5" data-testid="claim-filters">
      <button
        type="button"
        className={chip(filters.verdict === 'all' && !filters.pendingOnly)}
        onClick={() => setFilters({ verdict: 'all', pendingOnly: false })}
      >
        Todas · {claims.length}
      </button>
      {VERDICT_ORDER.filter((v) => counts[v] > 0).map((v) => {
        const Icon = VERDICT[v].icon
        return (
          <button
            key={v}
            type="button"
            className={chip(filters.verdict === v)}
            onClick={() => setFilters({ verdict: filters.verdict === v ? 'all' : v, pendingOnly: false })}
            data-testid={`filter-${v}`}
          >
            <Icon size={11} className={VERDICT[v].text} /> {VERDICT[v].label} · {counts[v]}
          </button>
        )
      })}
      {pending > 0 && (
        <button
          type="button"
          className={chip(filters.pendingOnly)}
          onClick={() => setFilters({ pendingOnly: !filters.pendingOnly, verdict: 'all' })}
        >
          <LoaderCircle size={11} /> Pendentes · {pending}
        </button>
      )}
      {speakers.length > 1 && (
        <select
          value={filters.speaker}
          onChange={(e) => setFilters({ speaker: e.target.value })}
          aria-label="Filtrar por falante"
          className="rounded border border-border bg-surface px-1.5 py-0.5 text-[11px] text-text"
        >
          <option value="all">Todos os falantes</option>
          {speakers.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      )}
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
  const filters = useClaims((s) => s.filters)
  const claims = visibleClaims(byId)
  const shown = applyFilters(claims, filters)

  return (
    <div className="flex h-full flex-col">
      <ExtractorNotice onOpenSettings={onOpenSettings} />
      {error && (
        <p role="alert" className="mb-3 text-xs text-verdict-false">
          {error}
        </p>
      )}
      <FilterBar claims={claims} />
      {claims.length === 0 ? (
        <EmptyState
          icon={<ListChecks size={32} strokeWidth={1.25} />}
          title="Nenhuma afirmação ainda"
          hint={
            hasSession
              ? 'As afirmações factuais detectadas aparecem aqui e são checadas automaticamente. Você também pode selecionar um trecho da transcrição e clicar em “Verificar trecho”.'
              : 'As afirmações factuais detectadas aparecem aqui com o veredicto e as fontes.'
          }
        />
      ) : shown.length === 0 ? (
        <p className="text-xs text-text-muted">Nenhuma afirmação com esse filtro.</p>
      ) : (
        <ul className="flex flex-col gap-2" data-testid="claims-list">
          {shown.map((c) => (
            <ClaimCard key={c.id} claim={c} focused={c.id === focusedId} seekable={seekable} />
          ))}
        </ul>
      )}
    </div>
  )
}
