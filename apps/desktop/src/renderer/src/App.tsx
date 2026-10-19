import { useState } from 'react'
import { FileAudio, ScrollText, Settings, X } from 'lucide-react'
import { ChecksPanel } from './components/ChecksPanel'
import { ContextBar } from './components/ContextBar'
import { ConnectionBadge } from './components/ConnectionBadge'
import { MediaPlayer } from './components/MediaPlayer'
import { EmptyState, Panel } from './components/Panel'
import { SessionsPanel } from './components/SessionsPanel'
import { SettingsDialog } from './components/SettingsDialog'
import { SourcePanel } from './components/SourcePanel'
import { SttBadge } from './components/SttBadge'
import { TranscriptView } from './components/TranscriptView'
import { sessionDate, sessionTitle } from './lib/session-label'
import { summarize, useConnection } from './store/connection'
import { useLibrary } from './store/library'
import { useSession } from './store/session'
import { useTranscript } from './store/transcript'

function TranscriptPanel(): React.JSX.Element {
  const active = useSession((s) => s.active)
  const viewing = useLibrary((s) => s.viewing)
  const closeViewing = useLibrary((s) => s.close)
  // Em andamento tem prioridade; senão, a sessão aberta (do histórico ou recém-encerrada).
  const shown = active?.info ?? viewing
  // Arquivo: player desde o início. Ao vivo: só depois de encerrar (a gravação ainda cresce).
  const playable = shown && (shown.source === 'file' || !active) ? shown : null
  const hasText = useTranscript((s) => s.segments.length > 0 || s.partial !== null)
  const stt = useTranscript((s) => s.stt)
  const waitingModel = active && stt && stt.state !== 'ready'

  const title = shown ? (
    <span className="flex min-w-0 items-baseline gap-2 normal-case tracking-normal">
      <span className="truncate text-sm font-semibold text-text" data-testid="shown-title">
        {sessionTitle(shown)}
      </span>
      <span className="shrink-0 text-xs font-normal text-text-muted">{sessionDate(shown)}</span>
    </span>
  ) : (
    'Transcrição'
  )

  return (
    <Panel
      title={title}
      aside={
        !active && viewing ? (
          <button
            type="button"
            onClick={closeViewing}
            aria-label="Fechar sessão"
            title="Fechar sessão"
            className="text-text-muted hover:text-text"
          >
            <X size={16} />
          </button>
        ) : null
      }
    >
      <div className="flex h-full flex-col gap-4">
        {playable && <MediaPlayer session={playable} />}
        {shown && <ContextBar session={shown} />}
        <div className="min-h-0 flex-1">
          {hasText ? (
            <TranscriptView seekable={playable !== null} />
          ) : (
            <EmptyState
              icon={<ScrollText size={32} strokeWidth={1.25} />}
              title={
                waitingModel
                  ? 'Preparando o modelo de transcrição…'
                  : active
                    ? 'Ouvindo…'
                    : viewing
                      ? 'Sessão sem transcrição'
                      : 'Nenhuma transcrição ainda'
              }
              hint={
                waitingModel
                  ? 'O áudio já está sendo gravado; a transcrição começa assim que o modelo estiver pronto.'
                  : active
                    ? 'A transcrição aparece aqui assim que alguém falar.'
                    : viewing
                      ? 'Nenhuma fala foi transcrita nesta sessão.'
                      : 'Escolha uma fonte de áudio para começar, ou abra uma sessão salva.'
              }
            />
          )}
        </div>
      </div>
    </Panel>
  )
}

function ChecksColumn({ onOpenSettings }: { onOpenSettings(): void }): React.JSX.Element {
  const active = useSession((s) => s.active)
  const viewing = useLibrary((s) => s.viewing)
  const shown = active?.info ?? viewing
  const seekable = shown !== null && (shown.source === 'file' || !active)
  return (
    <Panel title="Checagens">
      <ChecksPanel seekable={seekable} hasSession={shown !== null} onOpenSettings={onOpenSettings} />
    </Panel>
  )
}

type LeftTab = 'source' | 'sessions'

function LeftPanel(): React.JSX.Element {
  const [tab, setTab] = useState<LeftTab>('source')
  const tabClass = (t: LeftTab): string =>
    `rounded px-2 py-1 transition-colors ${tab === t ? 'bg-primary-soft text-primary-strong' : 'hover:text-text'}`
  return (
    <Panel
      title={
        <span className="flex gap-1" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'source'}
            className={tabClass('source')}
            onClick={() => setTab('source')}
          >
            Fonte
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'sessions'}
            className={tabClass('sessions')}
            onClick={() => setTab('sessions')}
            data-testid="tab-sessions"
          >
            Sessões
          </button>
        </span>
      }
    >
      {tab === 'source' ? <SourcePanel /> : <SessionsPanel />}
    </Panel>
  )
}

export function App(): React.JSX.Element {
  const [dragging, setDragging] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const connected = useConnection((s) => summarize(s.sidecar, s.socket) === 'connected')
  const canStart = useSession((s) => s.active === null && s.starting === null)
  const startFile = useSession((s) => s.startFile)

  const onDrop = async (e: React.DragEvent): Promise<void> => {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (!file || !connected || !canStart) return
    const path = await window.rtfc.registerDroppedFile(file)
    if (path) await startFile(path)
  }

  return (
    <div
      className="relative flex h-full flex-col"
      onDragOver={(e) => {
        e.preventDefault()
        if (e.dataTransfer.types.includes('Files')) setDragging(true)
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false)
      }}
      onDrop={(e) => void onDrop(e)}
    >
      <header className="flex items-center justify-between border-b border-border bg-surface px-6 py-3">
        <div className="flex items-baseline gap-3">
          <span className="text-xl font-semibold tracking-tight text-primary">rtfc</span>
          <span className="text-xs text-text-muted">Real Time Fact Checker</span>
        </div>
        <div className="flex items-center gap-2">
          <SttBadge />
          <ConnectionBadge />
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            aria-label="Configurações"
            title="Configurações"
            data-testid="open-settings"
            className="rounded-md p-1.5 text-text-muted hover:bg-primary-soft hover:text-primary"
          >
            <Settings size={17} strokeWidth={1.75} />
          </button>
        </div>
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)_380px] gap-4 p-4">
        <LeftPanel />

        <TranscriptPanel />

        <ChecksColumn onOpenSettings={() => setSettingsOpen(true)} />
      </main>

      <footer className="border-t border-border bg-surface px-6 py-2 text-[11px] text-text-muted">
        Veredictos gerados por IA — confira sempre as fontes.
      </footer>

      {settingsOpen && <SettingsDialog onClose={() => setSettingsOpen(false)} />}

      {dragging && (
        <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center bg-primary/10 backdrop-blur-[1px]">
          <div className="flex flex-col items-center gap-2 rounded-card border-2 border-dashed border-primary bg-surface px-10 py-8 text-primary">
            <FileAudio size={32} strokeWidth={1.25} />
            <span className="text-sm font-medium">
              {canStart ? 'Solte para checar este arquivo' : 'Encerre a sessão atual primeiro'}
            </span>
          </div>
        </div>
      )}
    </div>
  )
}
