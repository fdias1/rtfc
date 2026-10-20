// Sessões salvas e qual delas está aberta na tela.

import { create } from 'zustand'
import type { SessionInfo, SessionListItem } from '@rtfc/protocol'
import { backend, onServerMessage } from '../lib/connection'
import { useClaims } from './claims'
import { useTranscript } from './transcript'

interface LibraryState {
  items: SessionListItem[]
  loading: boolean
  error: string | null
  /** Sessão exibida (transcrição + player) quando não há sessão em andamento. */
  viewing: SessionInfo | null
  refresh(): Promise<void>
  open(sessionId: string): Promise<void>
  /** Mostra uma sessão que acabou de terminar, sem recarregar a transcrição (já está na tela). */
  showEnded(info: SessionInfo): void
  rename(sessionId: string, title: string): Promise<void>
  remove(sessionId: string): Promise<void>
  close(): void
  setContext(sessionId: string, text: string | null): Promise<string | null>
  generateContext(sessionId: string): Promise<string | null>
  /** Nomeia um falante (vazio volta para "Falante N"). Devolve a mensagem de erro, se houver. */
  renameSpeaker(sessionId: string, speaker: string, name: string | null): Promise<string | null>
  /** Refaz a identificação dos falantes a partir do áudio da sessão salva. */
  refineSpeakers(sessionId: string): Promise<string | null>
}

/** Refinar decodifica o áudio inteiro e analisa cada frase: pode levar minutos numa sessão longa. */
const REFINE_TIMEOUT_MS = 10 * 60_000

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export const useLibrary = create<LibraryState>((set, get) => ({
  items: [],
  loading: false,
  error: null,
  viewing: null,

  async refresh() {
    set({ loading: true })
    try {
      const reply = await backend.request({ type: 'session.list' })
      if (reply.type === 'session.list.result') {
        // A sessão aberta acompanha o que está no disco (ex.: marcada como interrompida após um crash).
        const viewing = get().viewing
        const fresh = viewing && reply.sessions.find((i) => i.session.id === viewing.id)?.session
        set({ items: reply.sessions, error: null, ...(fresh ? { viewing: fresh } : {}) })
      }
    } catch (err) {
      set({ error: errorMessage(err) })
    } finally {
      set({ loading: false })
    }
  },

  async open(sessionId) {
    const item = get().items.find((i) => i.session.id === sessionId)
    if (!item) return
    // Sessões de arquivo tocam o arquivo original, que precisa ser liberado de novo após reiniciar o app.
    await window.rtfc.allowSessionMedia(sessionId)
    const reply = await backend.request({ type: 'transcript.get', session_id: sessionId })
    if (reply.type !== 'transcript.result') return
    useTranscript.getState().load(sessionId, reply.segments)
    await useClaims.getState().load(sessionId)
    set({ viewing: item.session })
  },

  showEnded(info) {
    set({ viewing: info })
    void get().refresh()
    // O painel de checagens passa a oferecer a rechecagem com o modelo de qualidade.
    void useClaims.getState().refreshReview()
  },

  async rename(sessionId, title) {
    const reply = await backend.request({ type: 'session.rename', session_id: sessionId, title })
    if (reply.type !== 'session.updated') return
    set((s) => ({
      items: s.items.map((i) => (i.session.id === sessionId ? { ...i, session: reply.session } : i)),
      viewing: s.viewing?.id === sessionId ? reply.session : s.viewing
    }))
  },

  async remove(sessionId) {
    const reply = await backend.request({ type: 'session.delete', session_id: sessionId })
    if (reply.type === 'error') throw new Error(reply.message)
    set((s) => ({
      items: s.items.filter((i) => i.session.id !== sessionId),
      viewing: s.viewing?.id === sessionId ? null : s.viewing
    }))
    if (useTranscript.getState().sessionId === sessionId) {
      useTranscript.getState().reset('')
      useClaims.getState().reset('')
    }
  },

  async setContext(sessionId, text) {
    const reply = await backend.request({ type: 'session.set_context', session_id: sessionId, context: text })
    return reply.type === 'error' ? reply.message : null
  },

  async generateContext(sessionId) {
    const reply = await backend.request({ type: 'session.generate_context', session_id: sessionId })
    return reply.type === 'error' ? reply.message : null
  },

  async renameSpeaker(sessionId, speaker, name) {
    const reply = await backend.request({ type: 'speaker.rename', session_id: sessionId, speaker, name })
    return reply.type === 'error' ? reply.message : null
  },

  async refineSpeakers(sessionId) {
    try {
      const reply = await backend.request({ type: 'speakers.refine', session_id: sessionId }, REFINE_TIMEOUT_MS)
      return reply.type === 'error' ? reply.message : null
    } catch (err) {
      return errorMessage(err)
    }
  },

  close() {
    set({ viewing: null })
    useTranscript.getState().reset('')
    useClaims.getState().reset('')
  }
}))

// Metadados de sessões salvas mudaram (contexto, título…): atualiza a lista e a sessão aberta.
onServerMessage((msg) => {
  if (msg.type !== 'session.updated') return
  useLibrary.setState((s) => ({
    items: s.items.map((i) => (i.session.id === msg.session.id ? { ...i, session: msg.session } : i)),
    viewing: s.viewing?.id === msg.session.id ? msg.session : s.viewing
  }))
})
