import { useState } from 'react'
import { FileAudio, ListChecks, ScrollText } from 'lucide-react'
import { ConnectionBadge } from './components/ConnectionBadge'
import { MediaPlayer } from './components/MediaPlayer'
import { EmptyState, Panel } from './components/Panel'
import { SourcePanel } from './components/SourcePanel'
import { summarize, useConnection } from './store/connection'
import { useSession } from './store/session'

function TranscriptPanel(): React.JSX.Element {
  const active = useSession((s) => s.active)
  const last = useSession((s) => s.last)
  // Arquivo: player desde o início. Ao vivo: player da gravação depois de encerrar.
  const playable = active?.info.source === 'file' ? active.info : active ? null : last

  return (
    <Panel title="Transcrição">
      <div className="flex h-full flex-col gap-4">
        {playable && <MediaPlayer session={playable} />}
        <div className="min-h-0 flex-1">
          <EmptyState
            icon={<ScrollText size={32} strokeWidth={1.25} />}
            title={active ? 'Recebendo áudio…' : 'Nenhuma transcrição ainda'}
            hint={
              active
                ? 'A transcrição em tempo real chega no próximo marco (M2). O áudio já está sendo gravado.'
                : 'Escolha uma fonte de áudio para começar. A transcrição aparece aqui em tempo real.'
            }
          />
        </div>
      </div>
    </Panel>
  )
}

export function App(): React.JSX.Element {
  const [dragging, setDragging] = useState(false)
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
        <ConnectionBadge />
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-[280px_minmax(0,1fr)_380px] gap-4 p-4">
        <Panel title="Fonte">
          <SourcePanel />
        </Panel>

        <TranscriptPanel />

        <Panel title="Checagens">
          <EmptyState
            icon={<ListChecks size={32} strokeWidth={1.25} />}
            title="Nenhuma afirmação ainda"
            hint="As afirmações factuais detectadas aparecem aqui com o veredicto e as fontes."
          />
        </Panel>
      </main>

      <footer className="border-t border-border bg-surface px-6 py-2 text-[11px] text-text-muted">
        Veredictos gerados por IA — confira sempre as fontes.
      </footer>

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
