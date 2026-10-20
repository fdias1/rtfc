import { useEffect, useRef, useState } from 'react'
import { Download, LoaderCircle } from 'lucide-react'
import { backend } from '../lib/connection'

const FORMATS = [
  { id: 'md', label: 'Relatório (Markdown)', hint: 'Veredictos, fontes e transcrição' },
  { id: 'json', label: 'Dados completos (JSON)', hint: 'Tudo, para outras ferramentas' },
  { id: 'srt', label: 'Legendas SRT', hint: 'Com o nome de quem fala' },
  { id: 'vtt', label: 'Legendas WebVTT', hint: 'Com marcação de voz' }
] as const

/** Exporta a sessão aberta (M7). */
export function ExportMenu({ sessionId }: { sessionId: string }): React.JSX.Element {
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null)
  const box = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent): void => {
      if (!box.current?.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [open])

  useEffect(() => {
    if (!message) return
    const t = window.setTimeout(() => setMessage(null), 5000)
    return () => window.clearTimeout(t)
  }, [message])

  const run = async (format: (typeof FORMATS)[number]['id']): Promise<void> => {
    setOpen(false)
    setBusy(true)
    try {
      const reply = await backend.request({ type: 'session.export', session_id: sessionId, format }, 60_000)
      if (reply.type === 'error') throw new Error(reply.message)
      if (reply.type !== 'session.export.result') return
      const path = await window.rtfc.saveTextFile(reply.filename, reply.content)
      if (path) setMessage({ ok: true, text: `Salvo em ${path}` })
    } catch (err) {
      setMessage({ ok: false, text: `Não foi possível exportar: ${err instanceof Error ? err.message : err}` })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div ref={box} className="relative flex items-center gap-2">
      {message && (
        <span
          className={`max-w-72 truncate text-xs font-normal normal-case tracking-normal ${message.ok ? 'text-text-muted' : 'text-verdict-false'}`}
          title={message.text}
          data-testid="export-message"
        >
          {message.text}
        </span>
      )}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        disabled={busy}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Exportar a sessão"
        className="inline-flex items-center gap-1 text-xs font-normal normal-case tracking-normal text-primary hover:underline disabled:opacity-50"
        data-testid="export-button"
      >
        {busy ? <LoaderCircle size={14} className="animate-spin" /> : <Download size={14} />}
        Exportar
      </button>
      {open && (
        <ul
          role="menu"
          className="absolute top-full right-0 z-20 mt-1 w-64 rounded-md border border-border bg-surface py-1 shadow-lg"
        >
          {FORMATS.map((f) => (
            <li key={f.id}>
              <button
                type="button"
                role="menuitem"
                onClick={() => void run(f.id)}
                className="flex w-full flex-col px-3 py-1.5 text-left normal-case tracking-normal hover:bg-primary-soft/60"
                data-testid={`export-${f.id}`}
              >
                <span className="text-sm font-normal text-text">{f.label}</span>
                <span className="text-[11px] font-normal text-text-muted">{f.hint}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
