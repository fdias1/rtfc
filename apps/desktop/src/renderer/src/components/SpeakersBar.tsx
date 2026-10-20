import { useState } from 'react'
import { LoaderCircle, Pencil, Users } from 'lucide-react'
import type { SessionInfo } from '@rtfc/protocol'
import { speakerColor, speakerLabel, speakersInOrder } from '../lib/speakers'
import { useLibrary } from '../store/library'
import { useTranscript } from '../store/transcript'

function SpeakerChip({ session, id }: { session: SessionInfo; id: string }): React.JSX.Element {
  const rename = useLibrary((s) => s.renameSpeaker)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState('')
  const label = speakerLabel(id, session.speakers)!

  const save = async (): Promise<void> => {
    setEditing(false)
    const name = draft.trim()
    if (name !== (session.speakers[id] ?? '')) await rename(session.id, id, name || null)
  }

  if (editing) {
    return (
      <input
        autoFocus
        value={draft}
        maxLength={80}
        placeholder={speakerLabel(id)!}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => void save()}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void save()
          if (e.key === 'Escape') setEditing(false)
        }}
        className="w-36 rounded-full border border-primary bg-surface px-2 py-0.5 text-xs text-text"
        data-testid="speaker-name-input"
      />
    )
  }
  return (
    <button
      type="button"
      onClick={() => {
        setDraft(session.speakers[id] ?? '')
        setEditing(true)
      }}
      title="Dar nome a este falante"
      className={`group inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs ${speakerColor(id)}`}
      data-testid="speaker-chip"
      data-speaker={id}
    >
      {label}
      <Pencil size={10} className="opacity-40 group-hover:opacity-100" />
    </button>
  )
}

/** Falantes identificados na sessão exibida: renomear e refinar (M4). */
export function SpeakersBar({ session, live }: { session: SessionInfo; live: boolean }): React.JSX.Element | null {
  const ids = useTranscript((s) => speakersInOrder(s.segments.map((seg) => seg.speaker)).join(','))
  const refine = useLibrary((s) => s.refineSpeakers)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const speakers = ids ? ids.split(',') : []
  if (speakers.length === 0 && live) return null

  const onRefine = async (): Promise<void> => {
    setBusy(true)
    setError(null)
    const err = await refine(session.id)
    setBusy(false)
    if (err) setError(err)
  }

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs" data-testid="speakers-bar">
      <span className="inline-flex items-center gap-1 font-semibold tracking-wide text-text-muted uppercase">
        <Users size={12} /> Falantes
      </span>
      {speakers.length === 0 && <span className="text-text-muted">nenhum identificado</span>}
      {speakers.map((id) => (
        <SpeakerChip key={id} session={session} id={id} />
      ))}
      {!live && (
        <button
          type="button"
          onClick={() => void onRefine()}
          disabled={busy}
          title="Analisar de novo as vozes da sessão inteira (corrige falantes trocados ou duplicados)"
          className="ml-auto inline-flex items-center gap-1 text-primary hover:underline disabled:opacity-50"
          data-testid="refine-speakers"
        >
          {busy && <LoaderCircle size={12} className="animate-spin" />}
          {busy ? 'Refinando…' : 'Refinar falantes'}
        </button>
      )}
      {error && <span className="basis-full text-verdict-false">{error}</span>}
    </div>
  )
}
