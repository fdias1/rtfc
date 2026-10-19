// Transcrição da sessão em exibição: segmentos confirmados + trecho aberto (parcial).

import { create } from 'zustand'
import type { ServerMessage, SttStatusMessage, TranscriptSegmentData } from '@rtfc/protocol'
import { onServerMessage } from '../lib/connection'

interface Partial {
  startMs: number
  confirmed: string
  tentative: string
}

interface TranscriptState {
  sessionId: string | null
  segments: TranscriptSegmentData[]
  partial: Partial | null
  /** Latência do último segmento confirmado (ao vivo). */
  lastLatencyMs: number | null
  stt: SttStatusMessage | null
  reset(sessionId: string): void
  load(sessionId: string, segments: TranscriptSegmentData[]): void
  handle(msg: ServerMessage): void
}

export const useTranscript = create<TranscriptState>((set, get) => ({
  sessionId: null,
  segments: [],
  partial: null,
  lastLatencyMs: null,
  stt: null,

  reset(sessionId) {
    set({ sessionId, segments: [], partial: null, lastLatencyMs: null })
  },

  load(sessionId, segments) {
    set({ sessionId, segments, partial: null })
  },

  handle(msg) {
    if (msg.type === 'stt.status') {
      set({ stt: msg })
      return
    }
    const { sessionId } = get()
    if (msg.type === 'transcript.segment' && msg.session_id === sessionId) {
      set((s) => ({
        segments: [...s.segments, msg.segment],
        lastLatencyMs: msg.latency_ms ?? s.lastLatencyMs,
        // O parcial seguinte (que vem logo depois) já exclui o que foi fechado.
        partial: null
      }))
    } else if (msg.type === 'transcript.partial' && msg.session_id === sessionId) {
      set({
        partial:
          msg.confirmed || msg.tentative
            ? { startMs: msg.start_ms, confirmed: msg.confirmed, tentative: msg.tentative }
            : null
      })
    } else if (msg.type === 'session.ended' && msg.session.id === sessionId) {
      set({ partial: null })
    }
  }
}))

onServerMessage((msg) => useTranscript.getState().handle(msg))
