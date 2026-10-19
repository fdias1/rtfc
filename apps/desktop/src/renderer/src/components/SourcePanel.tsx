import { useEffect, useState } from 'react'
import { FileAudio, LoaderCircle, Mic, MonitorSpeaker, Pause, Play, Square, TriangleAlert } from 'lucide-react'
import { listMicrophones } from '../lib/audio/capture'
import { basename, formatDuration } from '../lib/format'
import { summarize, useConnection } from '../store/connection'
import { useSession, type LanguageChoice, type SourceKind } from '../store/session'
import { LevelMeter } from './LevelMeter'

const SOURCE_LABEL: Record<SourceKind, string> = {
  mic: 'Microfone',
  system: 'Áudio do sistema',
  file: 'Arquivo'
}

function SourceButton({
  icon: Icon,
  label,
  hint,
  onClick,
  disabled,
  loading,
  testId
}: {
  icon: typeof Mic
  label: string
  hint?: string
  onClick(): void
  disabled: boolean
  loading: boolean
  testId: string
}): React.JSX.Element {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      data-testid={testId}
      className="flex w-full items-start gap-3 rounded-md border border-border px-3 py-2.5 text-left text-sm text-text transition-colors hover:border-primary/40 hover:bg-primary-soft/60 disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-transparent"
    >
      {loading ? (
        <LoaderCircle size={18} strokeWidth={1.5} className="mt-0.5 shrink-0 animate-spin text-primary" />
      ) : (
        <Icon size={18} strokeWidth={1.5} className="mt-0.5 shrink-0 text-primary" />
      )}
      <span className="flex flex-col">
        {label}
        {hint && <span className="text-xs text-text-muted">{hint}</span>}
      </span>
    </button>
  )
}

function MicrophoneSelect({
  value,
  onChange,
  disabled
}: {
  value: string
  onChange(id: string): void
  disabled: boolean
}): React.JSX.Element | null {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([])

  useEffect(() => {
    const refresh = (): void => void listMicrophones().then(setDevices)
    refresh()
    navigator.mediaDevices.addEventListener('devicechange', refresh)
    return () => navigator.mediaDevices.removeEventListener('devicechange', refresh)
  }, [])

  // Sem permissão os rótulos vêm vazios; depois da primeira captura a lista se completa.
  if (devices.length < 2 && !devices.some((d) => d.label)) return null
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      aria-label="Microfone"
      className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-text"
    >
      <option value="">Microfone padrão do sistema</option>
      {devices
        .filter((d) => d.deviceId && d.deviceId !== 'default')
        .map((d) => (
          <option key={d.deviceId} value={d.deviceId}>
            {d.label || 'Microfone sem nome'}
          </option>
        ))}
    </select>
  )
}

function ActiveSession(): React.JSX.Element | null {
  const active = useSession((s) => s.active)
  const stop = useSession((s) => s.stop)
  const togglePause = useSession((s) => s.togglePause)
  if (!active) return null

  const { info } = active
  const live = info.source !== 'file'
  // Captura feita pelo backend (Linux): sem stream na UI, logo sem VU meter nem pausa.
  const uiCapture = active.capture !== undefined
  const fraction = active.totalMs ? Math.min(1, active.processedMs / active.totalMs) : 0

  return (
    <div
      className="flex flex-col gap-3 rounded-md border border-primary/30 bg-primary-soft/50 p-3"
      data-testid="active-session"
    >
      <div className="flex items-center justify-between">
        <span className="flex items-center gap-2 text-sm font-medium text-primary-strong">
          {live && (
            <span
              className={`h-2 w-2 rounded-full ${active.paused ? 'bg-text-muted' : 'animate-pulse bg-verdict-false'}`}
              aria-hidden
            />
          )}
          {live ? (active.paused ? 'Pausado' : 'Gravando') : 'Processando'} · {SOURCE_LABEL[info.source]}
        </span>
        <span className="font-mono text-xs text-text-muted" data-testid="session-elapsed">
          {formatDuration(active.processedMs)}
          {!live && active.totalMs ? ` / ${formatDuration(active.totalMs)}` : ''}
        </span>
      </div>

      {live ? (
        uiCapture && <LevelMeter />
      ) : (
        <>
          <p className="truncate text-xs text-text-muted" title={info.file_path ?? undefined}>
            {basename(info.file_path ?? '')}
          </p>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-primary-soft">
            <div className="h-full bg-primary transition-[width]" style={{ width: `${fraction * 100}%` }} />
          </div>
        </>
      )}

      <div className="flex gap-2">
        {uiCapture && (
          <button
            type="button"
            onClick={togglePause}
            className="flex flex-1 items-center justify-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-text hover:bg-primary-soft"
          >
            {active.paused ? <Play size={14} /> : <Pause size={14} />}
            {active.paused ? 'Retomar' : 'Pausar'}
          </button>
        )}
        <button
          type="button"
          onClick={() => void stop()}
          data-testid="stop-session"
          className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-primary px-2 py-1.5 text-xs font-medium text-white hover:bg-primary-strong"
        >
          <Square size={12} fill="currentColor" />
          {live ? 'Encerrar' : 'Cancelar'}
        </button>
      </div>
    </div>
  )
}

function ErrorNotice(): React.JSX.Element | null {
  const error = useSession((s) => s.error)
  const code = useSession((s) => s.errorCode)
  const lastAttempt = useSession((s) => s.lastAttempt)
  const clear = useSession((s) => s.clearError)
  const privacyPane = lastAttempt === 'system' ? 'screen' : 'microphone'

  if (!error) return null
  return (
    <div
      role="alert"
      className="flex flex-col gap-2 rounded-md border border-verdict-false/30 bg-verdict-false/5 p-3 text-xs text-text"
    >
      <span className="flex items-start gap-2">
        <TriangleAlert size={14} className="mt-0.5 shrink-0 text-verdict-false" />
        {error}
      </span>
      <div className="flex gap-3">
        {code === 'permission' && window.rtfc.platform === 'darwin' && (
          <button
            type="button"
            className="text-primary underline"
            onClick={() => void window.rtfc.openPrivacySettings(privacyPane)}
          >
            Abrir Ajustes de Privacidade
          </button>
        )}
        <button type="button" className="text-text-muted underline" onClick={clear}>
          Fechar
        </button>
      </div>
    </div>
  )
}

const LANGUAGES: { value: LanguageChoice; label: string }[] = [
  { value: 'pt', label: 'Português' },
  { value: 'en', label: 'Inglês' },
  { value: 'es', label: 'Espanhol' },
  { value: 'auto', label: 'Detectar automaticamente' }
]

function LanguageSelect({ disabled }: { disabled: boolean }): React.JSX.Element {
  const language = useSession((s) => s.language)
  const setLanguage = useSession((s) => s.setLanguage)
  return (
    <label className="flex flex-col gap-1 text-xs text-text-muted">
      Idioma do discurso
      <select
        value={language}
        onChange={(e) => setLanguage(e.target.value as LanguageChoice)}
        disabled={disabled}
        data-testid="language-select"
        className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-text"
      >
        {LANGUAGES.map((l) => (
          <option key={l.value} value={l.value}>
            {l.label}
          </option>
        ))}
      </select>
    </label>
  )
}

function ContextDraft({ disabled }: { disabled: boolean }): React.JSX.Element {
  const value = useSession((s) => s.contextDraft)
  const setValue = useSession((s) => s.setContextDraft)
  return (
    <label className="flex flex-col gap-1 text-xs text-text-muted">
      Contexto do conteúdo (opcional)
      <textarea
        value={value}
        onChange={(e) => setValue(e.target.value)}
        disabled={disabled}
        rows={3}
        maxLength={2000}
        placeholder="Ex.: Debate presidencial na TV, candidatos A e B, out/2026. Se ficar vazio, o rtfc descobre pela transcrição."
        className="w-full rounded-md border border-border bg-surface px-2 py-1.5 text-xs text-text"
        data-testid="context-draft"
      />
    </label>
  )
}

export function SourcePanel(): React.JSX.Element {
  const connected = useConnection((s) => summarize(s.sidecar, s.socket) === 'connected')
  const active = useSession((s) => s.active)
  const starting = useSession((s) => s.starting)
  const startLive = useSession((s) => s.startLive)
  const startFile = useSession((s) => s.startFile)
  const [micId, setMicId] = useState('')

  const busy = !connected || active !== null || starting !== null
  const linux = window.rtfc.platform === 'linux'

  const openFile = async (): Promise<void> => {
    const path = await window.rtfc.openMediaFile()
    if (path) await startFile(path)
  }

  return (
    <div className="flex flex-col gap-4">
      <ActiveSession />
      <ErrorNotice />
      <LanguageSelect disabled={active !== null || starting !== null} />
      <ContextDraft disabled={active !== null || starting !== null} />

      <div className="flex flex-col gap-2">
        <SourceButton
          icon={Mic}
          label="Microfone"
          onClick={() => void startLive('mic', micId || undefined)}
          disabled={busy}
          loading={starting === 'mic'}
          testId="start-mic"
        />
        <MicrophoneSelect value={micId} onChange={setMicId} disabled={busy} />
      </div>

      <SourceButton
        icon={MonitorSpeaker}
        label="Áudio do sistema"
        hint={linux ? 'Experimental no Linux (PulseAudio/PipeWire)' : 'Live, podcast, vídeo tocando no computador'}
        onClick={() => void startLive('system')}
        disabled={busy}
        loading={starting === 'system'}
        testId="start-system"
      />

      <SourceButton
        icon={FileAudio}
        label="Arquivo de áudio ou vídeo"
        hint="Ou arraste o arquivo para a janela"
        onClick={() => void openFile()}
        disabled={busy}
        loading={starting === 'file'}
        testId="start-file"
      />
    </div>
  )
}
