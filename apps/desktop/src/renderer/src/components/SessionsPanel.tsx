import { useEffect, useState } from 'react'
import { FolderOpen, Pencil, Trash2, TriangleAlert } from 'lucide-react'
import type { SessionListItem } from '@rtfc/protocol'
import { formatDuration } from '../lib/format'
import { formatBytes, sessionDate, sessionTitle, sourceLabel } from '../lib/session-label'
import { summarize, useConnection } from '../store/connection'
import { useLibrary } from '../store/library'
import { useSession } from '../store/session'
import { Dialog, buttonClass } from './Dialog'

function RenameInput({ item, onDone }: { item: SessionListItem; onDone(): void }): React.JSX.Element {
  const rename = useLibrary((s) => s.rename)
  const [value, setValue] = useState(item.session.title ?? sessionTitle(item.session))
  const save = async (): Promise<void> => {
    if (value.trim() !== sessionTitle(item.session)) await rename(item.session.id, value)
    onDone()
  }
  return (
    <input
      autoFocus
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={() => void save()}
      onKeyDown={(e) => {
        e.stopPropagation()
        if (e.key === 'Enter') e.currentTarget.blur() // o onBlur salva (uma vez só)
        if (e.key === 'Escape') onDone()
      }}
      onClick={(e) => e.stopPropagation()}
      maxLength={200}
      aria-label="Nome da sessão"
      data-testid="rename-input"
      className="w-full rounded border border-primary/40 bg-surface px-1.5 py-0.5 text-sm text-text outline-none"
    />
  )
}

function SessionRow({
  item,
  selected,
  disabled,
  onDelete
}: {
  item: SessionListItem
  selected: boolean
  disabled: boolean
  onDelete(): void
}): React.JSX.Element {
  const open = useLibrary((s) => s.open)
  const [renaming, setRenaming] = useState(false)
  const { session } = item
  const flag = session.status === 'interrupted' ? 'interrompida' : session.status === 'error' ? 'erro' : null

  return (
    <li>
      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        aria-disabled={disabled}
        onClick={() => !disabled && !renaming && void open(session.id)}
        onKeyDown={(e) => {
          // Só o Enter na própria linha abre; o do campo de renomear não.
          if (e.key === 'Enter' && e.target === e.currentTarget && !disabled) void open(session.id)
        }}
        data-testid="session-row"
        data-session-id={session.id}
        className={`group flex flex-col gap-1 rounded-md border px-3 py-2 text-left transition-colors ${
          selected ? 'border-primary/40 bg-primary-soft/60' : 'border-transparent hover:bg-primary-soft/40'
        } ${disabled ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
      >
        <div className="flex items-start justify-between gap-2">
          {renaming ? (
            <RenameInput item={item} onDone={() => setRenaming(false)} />
          ) : (
            <span className="truncate text-sm font-medium text-text" title={sessionTitle(session)}>
              {sessionTitle(session)}
            </span>
          )}
          {!renaming && !disabled && (
            <span className="flex shrink-0 gap-1 opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100">
              <button
                type="button"
                aria-label="Renomear"
                title="Renomear"
                data-testid="rename-session"
                onClick={(e) => {
                  e.stopPropagation()
                  setRenaming(true)
                }}
                className="text-text-muted hover:text-primary"
              >
                <Pencil size={13} />
              </button>
              <button
                type="button"
                aria-label="Abrir pasta"
                title="Abrir pasta da sessão"
                onClick={(e) => {
                  e.stopPropagation()
                  void window.rtfc.revealSession(session.id)
                }}
                className="text-text-muted hover:text-primary"
              >
                <FolderOpen size={13} />
              </button>
              <button
                type="button"
                aria-label="Apagar"
                title="Apagar sessão"
                data-testid="delete-session"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete()
                }}
                className="text-text-muted hover:text-verdict-false"
              >
                <Trash2 size={13} />
              </button>
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-x-2 text-[11px] text-text-muted">
          <span>{sessionDate(session)}</span>
          <span>·</span>
          <span>{sourceLabel(session)}</span>
          {session.duration_ms != null && (
            <>
              <span>·</span>
              <span className="font-mono">{formatDuration(session.duration_ms)}</span>
            </>
          )}
          <span>·</span>
          <span>{formatBytes(item.size_bytes)}</span>
          {flag && (
            <span className="inline-flex items-center gap-0.5 text-verdict-context">
              <TriangleAlert size={11} /> {flag}
            </span>
          )}
        </div>
      </div>
    </li>
  )
}

export function SessionsPanel(): React.JSX.Element {
  const connected = useConnection((s) => summarize(s.sidecar, s.socket) === 'connected')
  const items = useLibrary((s) => s.items)
  const loading = useLibrary((s) => s.loading)
  const viewing = useLibrary((s) => s.viewing)
  const refresh = useLibrary((s) => s.refresh)
  const remove = useLibrary((s) => s.remove)
  const busy = useSession((s) => s.active !== null || s.starting !== null)
  const [toDelete, setToDelete] = useState<SessionListItem | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (connected) void refresh()
  }, [connected, refresh])

  if (!loading && items.length === 0) {
    return <p className="text-xs text-text-muted">Nenhuma sessão salva ainda.</p>
  }

  return (
    <>
      {busy && <p className="mb-2 text-xs text-text-muted">Encerre a sessão atual para abrir outra.</p>}
      <ul className="flex flex-col gap-1" data-testid="sessions-list">
        {items.map((item) => (
          <SessionRow
            key={item.session.id}
            item={item}
            selected={viewing?.id === item.session.id}
            disabled={busy}
            onDelete={() => setToDelete(item)}
          />
        ))}
      </ul>

      {toDelete && (
        <Dialog
          title="Apagar sessão?"
          onClose={() => setToDelete(null)}
          footer={
            <>
              <button type="button" className={buttonClass.secondary} onClick={() => setToDelete(null)}>
                Cancelar
              </button>
              <button
                type="button"
                className={buttonClass.danger}
                data-testid="confirm-delete"
                onClick={() => {
                  const id = toDelete.session.id
                  setToDelete(null)
                  remove(id).catch((err: unknown) => setError(err instanceof Error ? err.message : String(err)))
                }}
              >
                Apagar
              </button>
            </>
          }
        >
          <p>
            <strong>{sessionTitle(toDelete.session)}</strong> ({sessionDate(toDelete.session)}) será apagada: gravação,
            transcrição e legendas ({formatBytes(toDelete.size_bytes)}).
          </p>
          {toDelete.session.source === 'file' && (
            <p className="mt-2 text-text-muted">O arquivo original não é apagado.</p>
          )}
          <p className="mt-2 text-text-muted">Essa ação não pode ser desfeita.</p>
        </Dialog>
      )}
      {error && (
        <p role="alert" className="mt-2 text-xs text-verdict-false">
          {error}
        </p>
      )}
    </>
  )
}
