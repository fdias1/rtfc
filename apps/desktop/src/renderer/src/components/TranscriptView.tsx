import { useEffect, useRef, useState } from 'react'
import { formatDuration } from '../lib/format'
import { useTranscript } from '../store/transcript'

/** Distância do fim (px) abaixo da qual o autoscroll continua ligado. */
const STICKY_PX = 48

export function TranscriptView(): React.JSX.Element {
  const segments = useTranscript((s) => s.segments)
  const partial = useTranscript((s) => s.partial)
  const latency = useTranscript((s) => s.lastLatencyMs)
  const scroller = useRef<HTMLDivElement>(null)
  const [sticky, setSticky] = useState(true)

  // Autoscroll que pausa quando o usuário rola para cima (volta ao chegar no fim).
  useEffect(() => {
    const el = scroller.current
    if (el && sticky) el.scrollTop = el.scrollHeight
  }, [segments, partial, sticky])

  return (
    <div
      ref={scroller}
      onScroll={(e) => {
        const el = e.currentTarget
        setSticky(el.scrollHeight - el.scrollTop - el.clientHeight < STICKY_PX)
      }}
      className="h-full overflow-y-auto pr-2"
      data-testid="transcript"
    >
      <ol className="flex flex-col gap-3">
        {segments.map((seg) => (
          <li key={seg.index} className="grid grid-cols-[4.5rem_1fr] gap-3" data-testid="transcript-segment">
            <span className="pt-0.5 font-mono text-xs text-text-muted">{formatDuration(seg.start_ms)}</span>
            <p className="text-[16.5px] leading-relaxed text-text">{seg.text}</p>
          </li>
        ))}
        {partial && (
          <li className="grid grid-cols-[4.5rem_1fr] gap-3" data-testid="transcript-partial">
            <span className="pt-0.5 font-mono text-xs text-text-muted">{formatDuration(partial.startMs)}</span>
            <p className="text-[16.5px] leading-relaxed">
              <span className="text-text">{partial.confirmed}</span>
              {partial.confirmed && partial.tentative ? ' ' : ''}
              <span className="text-text-muted/70">{partial.tentative}</span>
            </p>
          </li>
        )}
      </ol>
      {latency !== null && (
        <p className="mt-4 text-right font-mono text-[11px] text-text-muted/70" data-testid="latency">
          latência {(latency / 1000).toFixed(1)} s
        </p>
      )}
      {!sticky && (
        <button
          type="button"
          onClick={() => setSticky(true)}
          className="sticky bottom-2 left-full mt-2 rounded-full border border-border bg-surface px-3 py-1 text-xs text-primary shadow-sm"
        >
          Ir para o fim
        </button>
      )}
    </div>
  )
}
