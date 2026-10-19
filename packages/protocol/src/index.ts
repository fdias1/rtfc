export * from './generated'

import type { ServerMessage } from './generated'

export const PROTOCOL_VERSION = 1

/** Faz o parse de uma mensagem do servidor. Valida só o envelope (`type`); o conteúdo é confiado ao backend. */
export function parseServerMessage(raw: string): ServerMessage | null {
  try {
    const msg: unknown = JSON.parse(raw)
    if (typeof msg === 'object' && msg !== null && typeof (msg as { type?: unknown }).type === 'string') {
      return msg as ServerMessage
    }
  } catch {
    // mensagem malformada: ignorada pelo chamador
  }
  return null
}
