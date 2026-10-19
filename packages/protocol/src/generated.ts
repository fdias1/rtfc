/* eslint-disable */
// GERADO por packages/protocol/scripts/gen.mjs a partir de backend/src/rtfc/protocol.
// Não edite à mão: rode `pnpm protocol:gen`.

/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClientMessage".
 */
export type ClientMessage =
  | Ping
  | EchoRequest
  | SessionStart
  | SessionStop
  | TranscriptGet
  | SessionList
  | SessionRename
  | SessionDelete
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ServerMessage".
 */
export type ServerMessage =
  | Hello
  | Pong
  | EchoReply
  | ErrorMessage
  | SessionStarted
  | SessionProgress
  | SessionEnded
  | SessionUpdated
  | SessionListResult
  | SessionDeleted
  | TranscriptSegment
  | TranscriptPartial
  | TranscriptResult
  | SttStatusMessage

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
  language: string | null
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
 * Pede a transcrição completa de uma sessão (ao reabrir).
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "TranscriptGet".
 */
export interface TranscriptGet {
  id: string
  session_id: string
  type: 'transcript.get'
}
/**
 * Lista as sessões salvas, da mais recente para a mais antiga.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionList".
 */
export interface SessionList {
  id: string
  type: 'session.list'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionRename".
 */
export interface SessionRename {
  id: string
  session_id: string
  title: string | null
  type: 'session.rename'
}
/**
 * Apaga a pasta da sessão e a transcrição. Nunca toca no arquivo original.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionDelete".
 */
export interface SessionDelete {
  id: string
  session_id: string
  type: 'session.delete'
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
  language: string | null
  media_kind: 'audio' | 'video'
  source: 'mic' | 'system' | 'file'
  started_at: string
  status: 'recording' | 'processing' | 'completed' | 'interrupted' | 'error'
  stt_engine: string | null
  stt_model: string | null
  title: string | null
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
/**
 * Metadados da sessão mudaram (idioma detectado, título renomeado…).
 *
 * Tem `id` quando é a resposta a um `session.rename`.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionUpdated".
 */
export interface SessionUpdated {
  id: string | null
  session: SessionInfo
  type: 'session.updated'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionListResult".
 */
export interface SessionListResult {
  id: string
  sessions: SessionListItem[]
  type: 'session.list.result'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionListItem".
 */
export interface SessionListItem {
  segment_count: number
  session: SessionInfo
  size_bytes: number
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionDeleted".
 */
export interface SessionDeleted {
  id: string
  session_id: string
  type: 'session.deleted'
}
/**
 * Um segmento (frase) confirmado. Não muda mais.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "TranscriptSegment".
 */
export interface TranscriptSegment {
  latency_ms: number | null
  segment: TranscriptSegmentData
  session_id: string
  type: 'transcript.segment'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "TranscriptSegmentData".
 */
export interface TranscriptSegmentData {
  end_ms: number
  index: number
  speaker: string | null
  start_ms: number
  text: string
  words: TranscriptWord[]
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "TranscriptWord".
 */
export interface TranscriptWord {
  end_ms: number
  prob: number
  start_ms: number
  text: string
}
/**
 * Trecho ainda aberto: `confirmed` não muda mais; `tentative` pode mudar na próxima passada.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "TranscriptPartial".
 */
export interface TranscriptPartial {
  confirmed: string
  session_id: string
  start_ms: number
  tentative: string
  type: 'transcript.partial'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "TranscriptResult".
 */
export interface TranscriptResult {
  id: string
  segments: TranscriptSegmentData[]
  session_id: string
  type: 'transcript.result'
}
/**
 * Estado do modelo de transcrição (download, carregamento, pronto, erro).
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SttStatusMessage".
 */
export interface SttStatusMessage {
  engine: string
  message: string | null
  model: string
  progress: number | null
  state: 'idle' | 'downloading' | 'loading' | 'ready' | 'error'
  type: 'stt.status'
}
