import { FileAudio, ListChecks, Mic, MonitorSpeaker, ScrollText } from 'lucide-react'
import { ConnectionBadge } from './components/ConnectionBadge'
import { EmptyState, Panel } from './components/Panel'

const SOURCES = [
  { icon: Mic, label: 'Microfone' },
  { icon: MonitorSpeaker, label: 'Áudio do sistema' },
  { icon: FileAudio, label: 'Arquivo de áudio ou vídeo' }
]

export function App(): React.JSX.Element {
  return (
    <div className="flex h-full flex-col">
      <header className="flex items-center justify-between border-b border-border bg-surface px-6 py-3">
        <div className="flex items-baseline gap-3">
          <span className="text-xl font-semibold tracking-tight text-primary">rtfc</span>
          <span className="text-xs text-text-muted">Real Time Fact Checker</span>
        </div>
        <ConnectionBadge />
      </header>

      <main className="grid min-h-0 flex-1 grid-cols-[260px_minmax(0,1fr)_380px] gap-4 p-4">
        <Panel title="Fonte">
          <div className="flex flex-col gap-2">
            {SOURCES.map(({ icon: Icon, label }) => (
              <button
                key={label}
                type="button"
                disabled
                title="Disponível no M1"
                className="flex items-center gap-3 rounded-md border border-border px-3 py-2.5 text-left text-sm text-text disabled:cursor-not-allowed disabled:opacity-50"
              >
                <Icon size={18} strokeWidth={1.5} className="text-primary" />
                {label}
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="Transcrição">
          <EmptyState
            icon={<ScrollText size={32} strokeWidth={1.25} />}
            title="Nenhuma sessão ativa"
            hint="Escolha uma fonte de áudio para começar. A transcrição aparece aqui em tempo real."
          />
        </Panel>

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
    </div>
  )
}
