import { AudioLines, Download, LoaderCircle, TriangleAlert } from 'lucide-react'
import { useTranscript } from '../store/transcript'

/** Estado do modelo de transcrição local (download na primeira vez, carregamento, pronto). */
export function SttBadge(): React.JSX.Element | null {
  const stt = useTranscript((s) => s.stt)
  if (!stt || stt.state === 'idle') return null

  const label =
    stt.state === 'downloading'
      ? `Baixando modelo ${stt.model}${stt.progress != null ? ` · ${Math.round(stt.progress * 100)}%` : '…'}`
      : stt.state === 'loading'
        ? `Carregando modelo ${stt.model}…`
        : stt.state === 'error'
          ? 'Falha no modelo de transcrição'
          : `Whisper ${stt.model}`

  return (
    <span
      data-testid="stt-status"
      data-state={stt.state}
      title={stt.message ?? `${stt.engine} · ${stt.model}`}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs ${
        stt.state === 'error' ? 'bg-verdict-false/10 text-verdict-false' : 'bg-border/50 text-text-muted'
      }`}
    >
      {stt.state === 'downloading' && <Download size={13} strokeWidth={1.75} />}
      {stt.state === 'loading' && <LoaderCircle size={13} strokeWidth={1.75} className="animate-spin" />}
      {stt.state === 'ready' && <AudioLines size={13} strokeWidth={1.75} />}
      {stt.state === 'error' && <TriangleAlert size={13} strokeWidth={1.75} />}
      {label}
    </span>
  )
}
