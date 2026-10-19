/* eslint-disable */
// GERADO por packages/protocol/scripts/gen.mjs a partir de backend/src/rtfc/protocol.
// Não edite à mão: rode `pnpm protocol:gen`.

/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClientMessage".
 */
export type ClientMessage = Ping | EchoRequest | SessionStart | SessionStop
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ServerMessage".
 */
export type ServerMessage =
  Hello | Pong | EchoReply | ErrorMessage | SessionStarted | SessionProgress | SessionEnded

/**
 * rtfc protocol v1
 */
export interface RtfcProtocol {
  client?: ClientMessage
  server?: ServerMessage
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "Ping".
 */
export interface Ping {
  id: string
  type: 'ping'
}
/**
 * Mensagem de exemplo do M0: o servidor devolve o mesmo texto.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "EchoRequest".
 */
export interface EchoRequest {
  id: string
  text: string
  type: 'echo'
}
/**
 * Inicia uma sessão.
 *
 * - `mic`/`system` com `capture="ui"`: a UI envia PCM s16le mono `sample_rate` em frames
 *   binários no mesmo WebSocket, até o `session.stop`.
 * - `system` com `capture="backend"`: o backend captura sozinho (fallback do Linux).
 * - `file`: o backend decodifica `file_path`.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionStart".
 */
export interface SessionStart {
  capture: 'ui' | 'backend'
  file_path: string | null
  id: string
  sample_rate: number
  source: 'mic' | 'system' | 'file'
  type: 'session.start'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionStop".
 */
export interface SessionStop {
  id: string
  session_id: string
  type: 'session.stop'
}
/**
 * Enviada pelo servidor assim que a conexão é aceita.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "Hello".
 */
export interface Hello {
  protocol_version: number
  server_version: string
  type: 'hello'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "Pong".
 */
export interface Pong {
  id: string
  type: 'pong'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "EchoReply".
 */
export interface EchoReply {
  id: string
  text: string
  type: 'echo.reply'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ErrorMessage".
 */
export interface ErrorMessage {
  code: string
  id: string | null
  message: string
  type: 'error'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionStarted".
 */
export interface SessionStarted {
  id: string
  session: SessionInfo
  type: 'session.started'
}
/**
 * Estado de uma sessão (também é o conteúdo de `session.json` na pasta da sessão).
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionInfo".
 */
export interface SessionInfo {
  audio_path: string
  dir: string
  duration_ms: number | null
  ended_at: string | null
  file_path: string | null
  id: string
  media_kind: 'audio' | 'video'
  source: 'mic' | 'system' | 'file'
  started_at: string
  status: 'recording' | 'processing' | 'completed' | 'interrupted' | 'error'
}
/**
 * Progresso: tempo de áudio já recebido (ao vivo) ou decodificado (arquivo).
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionProgress".
 */
export interface SessionProgress {
  processed_ms: number
  session_id: string
  total_ms: number | null
  type: 'session.progress'
}
/**
 * Fim de uma sessão. Tem `id` quando é a resposta a um `session.stop`.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionEnded".
 */
export interface SessionEnded {
  error: string | null
  id: string | null
  reason: 'stopped' | 'completed' | 'error'
  session: SessionInfo
  type: 'session.ended'
}
