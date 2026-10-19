import { useState } from 'react'
import { LoaderCircle, Pencil, Sparkles } from 'lucide-react'
import type { SessionInfo } from '@rtfc/protocol'
import { useLibrary } from '../store/library'
import { buttonClass } from './Dialog'

/** Contexto do conteúdo da sessão exibida: guia a seleção e a checagem das afirmações. */
export function ContextBar({ session }: { session: SessionInfo }): React.JSX.Element {
  const setContext = useLibrary((s) => s.setContext)
  const generate = useLibrary((s) => s.generateContext)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(session.context ?? '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const run = async (op: () => Promise<string | null>): Promise<void> => {
    setBusy(true)
    setError(null)
    const err = await op()
    setBusy(false)
    if (err) setError(err)
    else setEditing(false)
  }

  const badge =
    session.context_source === 'user' ? 'definido por você' : session.context ? 'gerado automaticamente' : null

  return (
    <div className="rounded-md border border-border bg-bg/60 px-3 py-2 text-xs" data-testid="context-bar">
      <div className="flex items-center gap-2">
        <span className="font-semibold tracking-wide text-text-muted uppercase">Contexto</span>
        {badge && <span className="text-text-muted">· {badge}</span>}
        {busy && <LoaderCircle size={12} className="animate-spin text-text-muted" />}
        {!editing && (
          <span className="ml-auto flex gap-3">
            <button
              type="button"
              className="inline-flex items-center gap-1 text-primary hover:underline disabled:opacity-50"
              onClick={() => void run(() => generate(session.id))}
              disabled={busy}
              title="Gerar o contexto a partir da transcrição até agora"
              data-testid="generate-context"
            >
              <Sparkles size={12} /> Gerar da transcrição
            </button>
            <button
              type="button"
              className="inline-flex items-center gap-1 text-primary hover:underline"
              onClick={() => {
                // O rascunho parte do contexto atual (que pode ter mudado sozinho, se automático).
                setDraft(session.context ?? '')
                setEditing(true)
              }}
              data-testid="edit-context"
            >
              <Pencil size={12} /> Editar
            </button>
          </span>
        )}
      </div>
      {editing ? (
        <div className="mt-2 flex flex-col gap-2">
          <textarea
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            maxLength={2000}
            rows={3}
            placeholder="Ex.: Debate entre os candidatos A e B ao governo de SP, TV Cultura, outubro de 2026."
            className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-sm text-text"
            data-testid="context-input"
          />
          <div className="flex justify-end gap-2">
            <button type="button" className={buttonClass.secondary} onClick={() => setEditing(false)}>
              Cancelar
            </button>
            {session.context_source === 'user' && (
              <button
                type="button"
                className={buttonClass.secondary}
                onClick={() => void run(() => setContext(session.id, null))}
                title="Apagar o seu texto e deixar o rtfc gerar o contexto"
              >
                Usar automático
              </button>
            )}
            <button
              type="button"
              className={buttonClass.primary}
              disabled={busy}
              onClick={() => void run(() => setContext(session.id, draft.trim() || null))}
              data-testid="save-context"
            >
              Salvar
            </button>
          </div>
        </div>
      ) : (
        <p className="mt-1 leading-relaxed text-text" data-testid="context-text">
          {session.context ?? (
            <span className="text-text-muted">
              Ainda não definido. O rtfc gera um resumo depois do primeiro minuto de fala, ou você pode escrever o seu.
            </span>
          )}
        </p>
      )}
      {error && <p className="mt-1 text-verdict-false">{error}</p>}
    </div>
  )
}
