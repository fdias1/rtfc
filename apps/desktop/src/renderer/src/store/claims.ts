// Afirmações da sessão exibida, estado do extrator e afirmação em foco.

import { create } from 'zustand'
import type { ClaimData, ExtractorStatus, ServerMessage } from '@rtfc/protocol'
import { backend, onServerMessage } from '../lib/connection'
import type { TranscriptSelection } from './transcript'

interface ClaimsState {
  sessionId: string | null
  byId: Record<string, ClaimData>
  extractor: ExtractorStatus | null
  focusedId: string | null
  /** Pedido de checagem manual em andamento. */
  submitting: boolean
  error: string | null
  reset(sessionId: string): void
  load(sessionId: string): Promise<void>
  focus(claimId: string | null): void
  discard(claimId: string): Promise<void>
  checkSelection(sessionId: string, selection: TranscriptSelection): Promise<ClaimData | null>
  handle(msg: ServerMessage): void
}

/** Afirmações visíveis (sem as descartadas), na ordem em que foram ditas. */
export function visibleClaims(byId: Record<string, ClaimData>): ClaimData[] {
  return Object.values(byId)
    .filter((c) => c.status !== 'discarded')
    .sort((a, b) => a.start_ms - b.start_ms || a.id.localeCompare(b.id))
}

/** A palavra (segmento, índice) está dentro do trecho da afirmação? */
export function claimCovers(c: ClaimData, segment: number, word: number): boolean {
  const afterStart = segment > c.from_segment || (segment === c.from_segment && word >= c.from_word)
  const beforeEnd = segment < c.to_segment || (segment === c.to_segment && word <= c.to_word)
  return afterStart && beforeEnd
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export const useClaims = create<ClaimsState>((set, get) => ({
  sessionId: null,
  byId: {},
  extractor: null,
  focusedId: null,
  submitting: false,
  error: null,

  reset(sessionId) {
    set({ sessionId, byId: {}, extractor: null, focusedId: null, error: null })
  },

  async load(sessionId) {
    get().reset(sessionId)
    const reply = await backend.request({ type: 'claims.get', session_id: sessionId })
    if (reply.type === 'claims.result' && get().sessionId === sessionId) {
      set({ byId: Object.fromEntries(reply.claims.map((c) => [c.id, c])) })
    }
  },

  focus(claimId) {
    set({ focusedId: claimId })
  },

  async discard(claimId) {
    const reply = await backend.request({ type: 'claim.discard', claim_id: claimId })
    if (reply.type === 'claim.updated') get().handle(reply)
  },

  async checkSelection(sessionId, selection) {
    set({ submitting: true, error: null })
    try {
      const reply = await backend.request({
        type: 'claim.manual',
        session_id: sessionId,
        from_segment: selection.from.segment,
        from_word: selection.from.word,
        to_segment: selection.to.segment,
        to_word: selection.to.word
      })
      if (reply.type === 'error') throw new Error(reply.message)
      if (reply.type !== 'claim.updated') return null
      get().handle(reply)
      set({ focusedId: reply.claim.id })
      return reply.claim
    } catch (err) {
      set({ error: errorMessage(err) })
      return null
    } finally {
      set({ submitting: false })
    }
  },

  handle(msg) {
    if (msg.type === 'claim.updated' && msg.claim.session_id === get().sessionId) {
      set((s) => ({ byId: { ...s.byId, [msg.claim.id]: msg.claim } }))
    } else if (msg.type === 'extractor.status' && msg.session_id === get().sessionId) {
      set({ extractor: msg })
    }
  }
}))

onServerMessage((msg) => useClaims.getState().handle(msg))
