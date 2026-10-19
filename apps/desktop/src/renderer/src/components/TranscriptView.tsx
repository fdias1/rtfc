import { memo, useEffect, useRef, useState } from 'react'
import { SearchCheck } from 'lucide-react'
import type { TranscriptSegmentData } from '@rtfc/protocol'
import { formatDuration } from '../lib/format'
import { selectionFromDom } from '../lib/selection'
import { usePlayer } from '../store/player'
import { useTranscript } from '../store/transcript'

/** Distância do fim (px) abaixo da qual o autoscroll continua ligado. */
const STICKY_PX = 48

interface SegmentProps {
  segment: TranscriptSegmentData
  /** Índice da palavra tocando agora neste segmento (-1 = nenhuma; null = segmento fora do player). */
  activeWord: number | null
  seekable: boolean
  onSeek(ms: number): void
}

const Segment = memo(function Segment({ segment, activeWord, seekable, onSeek }: SegmentProps) {
  const active = activeWord !== null
  return (
    <li
      className={`grid grid-cols-[4.5rem_1fr] gap-3 rounded-md px-2 py-1 transition-colors ${
        active ? 'bg-primary-soft/70' : ''
      }`}
      data-testid="transcript-segment"
      data-active={active || undefined}
    >
      <button
        type="button"
        disabled={!seekable}
        onClick={() => onSeek(segment.start_ms)}
        title={seekable ? 'Ouvir a partir daqui' : undefined}
        className="h-fit pt-0.5 text-left font-mono text-xs text-text-muted enabled:hover:text-primary disabled:cursor-default"
        data-testid="segment-time"
      >
        {formatDuration(segment.start_ms)}
      </button>
      <p
        className={`text-[16.5px] leading-relaxed text-text ${seekable ? 'cursor-pointer' : ''}`}
        onClick={() => {
          // Clique simples busca o áudio; arrastar para selecionar não.
          if (seekable && window.getSelection()?.isCollapsed !== false) onSeek(segment.start_ms)
        }}
      >
        {segment.words.length > 0
          ? segment.words.map((w, i) => (
              <span key={i}>
                {i > 0 && ' '}
                <span
                  data-seg={segment.index}
                  data-word={i}
                  className={i === activeWord ? 'rounded-sm bg-primary/15 text-primary-strong' : undefined}
                >
                  {w.text}
                </span>
              </span>
            ))
          : segment.text}
      </p>
    </li>
  )
})

function activeWordIndex(seg: TranscriptSegmentData, ms: number): number | null {
  if (ms < seg.start_ms || ms >= seg.end_ms + 300) return null
  const i = seg.words.findIndex((w) => ms >= w.start_ms && ms < w.end_ms + 150)
  return i
}

function SelectionMenu({ top }: { top: number }): React.JSX.Element {
  const selection = useTranscript((s) => s.selection)!
  return (
    <div
      className="absolute right-4 z-10 flex items-center gap-2 rounded-md border border-border bg-surface px-2 py-1.5 shadow-md"
      style={{ top }}
      data-testid="selection-menu"
      onMouseDown={(e) => e.preventDefault()}
    >
      <span className="font-mono text-[11px] text-text-muted">
        {formatDuration(selection.startMs)}–{formatDuration(selection.endMs)}
      </span>
      <button
        type="button"
        disabled
        title="A checagem manual de trechos chega com a extração de afirmações (M5)."
        className="flex items-center gap-1.5 rounded bg-primary px-2 py-1 text-xs font-medium text-white disabled:opacity-50"
      >
        <SearchCheck size={13} />
        Verificar trecho
      </button>
    </div>
  )
}

export function TranscriptView({ seekable }: { seekable: boolean }): React.JSX.Element {
  const segments = useTranscript((s) => s.segments)
  const partial = useTranscript((s) => s.partial)
  const latency = useTranscript((s) => s.lastLatencyMs)
  const selection = useTranscript((s) => s.selection)
  const setSelection = useTranscript((s) => s.setSelection)
  const currentMs = usePlayer((s) => (seekable ? s.currentMs : -1))
  const playing = usePlayer((s) => s.playing)
  const seek = usePlayer((s) => s.seek)
  const scroller = useRef<HTMLDivElement>(null)
  const [sticky, setSticky] = useState(true)
  const [menuTop, setMenuTop] = useState(0)

  // Autoscroll que pausa quando o usuário rola para cima (volta ao chegar no fim).
  useEffect(() => {
    const el = scroller.current
    if (el && sticky && !seekable) el.scrollTop = el.scrollHeight
  }, [segments, partial, sticky, seekable])

  // Durante a reprodução, mantém o segmento tocando à vista.
  const activeIndex = seekable ? segments.findIndex((s) => activeWordIndex(s, currentMs) !== null) : -1
  useEffect(() => {
    if (!playing || activeIndex < 0) return
    scroller.current?.querySelector('[data-active]')?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [activeIndex, playing])

  const onMouseUp = (): void => {
    const root = scroller.current
    if (!root) return
    const sel = selectionFromDom(window.getSelection(), root, segments)
    setSelection(sel)
    if (sel) {
      const rect = window.getSelection()!.getRangeAt(0).getBoundingClientRect()
      const box = root.getBoundingClientRect()
      setMenuTop(Math.max(0, rect.top - box.top + root.scrollTop - 40))
    }
  }

  return (
    <div
      ref={scroller}
      onScroll={(e) => {
        const el = e.currentTarget
        setSticky(el.scrollHeight - el.scrollTop - el.clientHeight < STICKY_PX)
      }}
      onMouseUp={onMouseUp}
      className="relative h-full overflow-y-auto pr-2"
      data-testid="transcript"
    >
      {selection && <SelectionMenu top={menuTop} />}
      <ol className="flex flex-col gap-1">
        {segments.map((seg) => (
          <Segment
            key={seg.index}
            segment={seg}
            activeWord={seekable ? activeWordIndex(seg, currentMs) : null}
            seekable={seekable}
            onSeek={seek}
          />
        ))}
        {partial && (
          <li className="grid grid-cols-[4.5rem_1fr] gap-3 px-2 py-1" data-testid="transcript-partial">
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
      {!sticky && !seekable && (
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
