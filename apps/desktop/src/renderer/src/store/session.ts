// Sessão atual: captura ao vivo ou arquivo, progresso e resultado.

import { create } from 'zustand'
import type { ServerMessage, SessionInfo } from '@rtfc/protocol'
import { CaptureError, startCapture, type AudioLevel, type LiveCapture, type LiveSource } from '../lib/audio/capture'
import { backend, onServerMessage, onSocketClose } from '../lib/connection'
import { useClaims } from './claims'
import { useLibrary } from './library'
import { useTranscript } from './transcript'

export type SourceKind = LiveSource | 'file'

/** Idioma do discurso: código ISO 639-1 ou 'auto' (detecção na primeira fala). */
export type LanguageChoice = 'pt' | 'en' | 'es' | 'auto'

const LANGUAGE_KEY = 'rtfc.language'

function initialLanguage(): LanguageChoice {
  try {
    const saved = localStorage.getItem(LANGUAGE_KEY)
    if (saved === 'pt' || saved === 'en' || saved === 'es' || saved === 'auto') return saved
  } catch {
    // armazenamento indisponível: usa o padrão
  }
  return 'pt'
}

function languageParam(choice: LanguageChoice): string | null {
  return choice === 'auto' ? null : choice
}

interface ActiveSession {
  info: SessionInfo
  capture?: LiveCapture
  paused: boolean
  processedMs: number
  totalMs: number | null
}

interface SessionState {
  starting: SourceKind | null
  /** Fonte da última tentativa de início (para saber qual permissão abrir num erro). */
  lastAttempt: SourceKind | null
  active: ActiveSession | null
  error: string | null
  errorCode: CaptureError['code'] | 'backend' | null
  level: AudioLevel
  language: LanguageChoice
  setLanguage(language: LanguageChoice): void
  /** Contexto digitado antes de iniciar (vai junto no session.start). */
  contextDraft: string
  setContextDraft(text: string): void
  startLive(source: LiveSource, deviceId?: string): Promise<void>
  startFile(path: string): Promise<void>
  stop(): Promise<void>
  togglePause(): void
  clearError(): void
  handleServerMessage(msg: ServerMessage): void
  handleDisconnect(): void
}

const SILENCE: AudioLevel = { peak: 0, rms: 0 }

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

type SetState = (patch: Partial<SessionState>) => void

/** Linux: o Electron não tem loopback, então o backend captura o monitor do PulseAudio/PipeWire. */
async function startBackendCapture(set: SetState): Promise<void> {
  try {
    const reply = await backend.request({
      type: 'session.start',
      source: 'system',
      capture: 'backend',
      sample_rate: 48_000,
      file_path: null,
      language: languageParam(useSession.getState().language),
      context: useSession.getState().contextDraft.trim() || null
    })
    if (reply.type !== 'session.started') throw new Error(reply.type === 'error' ? reply.message : reply.type)
    useTranscript.getState().reset(reply.session.id)
    useClaims.getState().reset(reply.session.id)
    set({ starting: null, active: { info: reply.session, paused: false, processedMs: 0, totalMs: null } })
  } catch (err) {
    set({
      starting: null,
      error: `Não foi possível capturar o áudio do sistema: ${errorMessage(err)}`,
      errorCode: 'backend'
    })
  }
}

export const useSession = create<SessionState>((set, get) => ({
  starting: null,
  lastAttempt: null,
  active: null,
  error: null,
  errorCode: null,
  level: SILENCE,
  language: initialLanguage(),
  contextDraft: '',

  setContextDraft(contextDraft) {
    set({ contextDraft })
  },

  setLanguage(language) {
    set({ language })
    try {
      localStorage.setItem(LANGUAGE_KEY, language)
    } catch {
      // preferência não persiste, sem problema
    }
  },

  async startLive(source, deviceId) {
    if (get().active || get().starting) return
    set({ starting: source, lastAttempt: source, error: null, errorCode: null })

    if (source === 'system' && window.rtfc.platform === 'linux') {
      await startBackendCapture(set)
      return
    }

    if (source === 'mic' && !(await window.rtfc.ensureMicrophoneAccess())) {
      set({ starting: null, error: 'Sem permissão para usar o microfone.', errorCode: 'permission' })
      return
    }

    // A captura abre antes da sessão (o pedido de permissão pode demorar); os primeiros blocos
    // ficam na fila até o backend confirmar a sessão.
    const queue: ArrayBuffer[] = []
    let ready = false
    let capture: LiveCapture
    try {
      capture = await startCapture(source, {
        deviceId,
        onChunk: (pcm) => {
          if (ready) backend.sendBinary(pcm)
          else queue.push(pcm)
        },
        onLevel: (level) => set({ level }),
        onEnded: () => {
          set({ error: 'A captura de áudio foi interrompida pelo sistema.', errorCode: 'unavailable' })
          void get().stop()
        }
      })
    } catch (err) {
      set({
        starting: null,
        error: errorMessage(err),
        errorCode: err instanceof CaptureError ? err.code : 'unavailable'
      })
      return
    }

    try {
      const reply = await backend.request({
        type: 'session.start',
        source,
        capture: 'ui',
        sample_rate: capture.sampleRate,
        file_path: null,
        language: languageParam(get().language),
        context: get().contextDraft.trim() || null
      })
      if (reply.type !== 'session.started') throw new Error(reply.type === 'error' ? reply.message : reply.type)
      useTranscript.getState().reset(reply.session.id)
      useClaims.getState().reset(reply.session.id)
      useSession.setState({ contextDraft: '' })
      for (const pcm of queue.splice(0)) backend.sendBinary(pcm)
      ready = true
      set({
        starting: null,
        active: { info: reply.session, capture, paused: false, processedMs: 0, totalMs: null }
      })
    } catch (err) {
      await capture.stop()
      set({ starting: null, error: `Não foi possível iniciar a sessão: ${errorMessage(err)}`, errorCode: 'backend' })
    }
  },

  async startFile(path) {
    if (get().active || get().starting) return
    set({ starting: 'file', lastAttempt: 'file', error: null, errorCode: null })
    try {
      const reply = await backend.request({
        type: 'session.start',
        source: 'file',
        capture: 'ui',
        sample_rate: 48_000,
        file_path: path,
        language: languageParam(get().language),
        context: get().contextDraft.trim() || null
      })
      if (reply.type !== 'session.started') throw new Error(reply.type === 'error' ? reply.message : reply.type)
      useTranscript.getState().reset(reply.session.id)
      useClaims.getState().reset(reply.session.id)
      useSession.setState({ contextDraft: '' })
      set({
        starting: null,
        active: {
          info: reply.session,
          paused: false,
          processedMs: 0,
          totalMs: reply.session.duration_ms
        }
      })
    } catch (err) {
      set({ starting: null, error: errorMessage(err), errorCode: 'backend' })
    }
  },

  async stop() {
    const active = get().active
    if (!active) return
    await active.capture?.stop()
    set({ level: SILENCE })
    try {
      const reply = await backend.request({ type: 'session.stop', session_id: active.info.id })
      if (reply.type === 'session.ended') {
        set({ active: null })
        useLibrary.getState().showEnded(reply.session)
        return
      }
    } catch {
      // backend caiu: ele mesmo finaliza a gravação ao perder a conexão
    }
    set({ active: null })
    useLibrary.getState().showEnded(active.info)
  },

  togglePause() {
    const active = get().active
    if (!active?.capture) return
    const paused = !active.paused
    active.capture.setPaused(paused)
    set({ active: { ...active, paused } })
  },

  clearError() {
    set({ error: null, errorCode: null })
  },

  handleServerMessage(msg) {
    const active = get().active
    if (msg.type === 'session.updated' && active?.info.id === msg.session.id) {
      set({ active: { ...active, info: msg.session } })
    } else if (msg.type === 'session.progress' && active?.info.id === msg.session_id) {
      set({ active: { ...active, processedMs: msg.processed_ms, totalMs: msg.total_ms ?? active.totalMs } })
    } else if (msg.type === 'session.ended' && msg.id === null && active?.info.id === msg.session.id) {
      set({
        active: null,
        error: msg.reason === 'error' ? `Falha ao processar: ${msg.error ?? 'erro desconhecido'}` : get().error,
        errorCode: msg.reason === 'error' ? 'backend' : get().errorCode
      })
      useLibrary.getState().showEnded(msg.session)
    } else if (msg.type === 'error' && msg.code === 'recording_failed' && active) {
      set({ error: `A gravação falhou: ${msg.message}`, errorCode: 'backend' })
      void get().stop()
    }
  },

  handleDisconnect() {
    const active = get().active
    if (!active) return
    // O backend encerra e finaliza a sessão sozinho quando a conexão cai.
    void active.capture?.stop()
    set({
      active: null,
      level: SILENCE,
      error: 'A conexão com o backend caiu; a sessão foi encerrada e a gravação até aqui foi salva.',
      errorCode: 'backend'
    })
    useLibrary.getState().showEnded(active.info)
  }
}))

onServerMessage((msg) => useSession.getState().handleServerMessage(msg))
onSocketClose(() => useSession.getState().handleDisconnect())
