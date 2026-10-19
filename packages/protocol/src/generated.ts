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
  | SessionSetContext
  | SessionGenerateContext
  | ClaimsGet
  | ClaimManual
  | ClaimDiscard
  | SettingsGet
  | SettingsSet
  | SecretSet
  | LlmTest
  | LlmModels
  | CheckCancel
  | CheckRetry
  | SearchTest
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
  | ClaimUpdated
  | ClaimsResult
  | ExtractorStatus
  | SettingsResult
  | LlmTestResult
  | LlmModelsResult
  | SearchTestResult

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
  context: string | null
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
 * Define o contexto da sessão. `context=None` volta para o contexto automático.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionSetContext".
 */
export interface SessionSetContext {
  context: string | null
  id: string
  session_id: string
  type: 'session.set_context'
}
/**
 * Pede ao LLM um contexto a partir da transcrição até agora.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SessionGenerateContext".
 */
export interface SessionGenerateContext {
  id: string
  session_id: string
  type: 'session.generate_context'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClaimsGet".
 */
export interface ClaimsGet {
  id: string
  session_id: string
  type: 'claims.get'
}
/**
 * Checagem de um trecho escolhido pelo usuário (seleção na transcrição).
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClaimManual".
 */
export interface ClaimManual {
  from_segment: number
  from_word: number
  id: string
  session_id: string
  to_segment: number
  to_word: number
  type: 'claim.manual'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClaimDiscard".
 */
export interface ClaimDiscard {
  claim_id: string
  id: string
  type: 'claim.discard'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SettingsGet".
 */
export interface SettingsGet {
  id: string
  type: 'settings.get'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SettingsSet".
 */
export interface SettingsSet {
  id: string
  settings: SettingsData
  type: 'settings.set'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SettingsData".
 */
export interface SettingsData {
  auto_check: boolean
  auto_extract: boolean
  checker: LlmRoleData
  extractor: LlmRoleData
  min_claim_score: number
  search: SearchSettingsData
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "LlmRoleData".
 */
export interface LlmRoleData {
  base_url: string | null
  model: string
  provider: string
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SearchSettingsData".
 */
export interface SearchSettingsData {
  blocked_domains: string[]
  fallback_duckduckgo: boolean
  provider: 'searxng' | 'duckduckgo' | 'tavily'
  searxng_url: string
}
/**
 * Grava (ou apaga, com `value=None`) a chave de API de um provedor no cofre do SO.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SecretSet".
 */
export interface SecretSet {
  id: string
  provider: string
  type: 'secret.set'
  value: string | null
}
/**
 * Testa a conexão do papel `role` com a configuração dada (ou a salva).
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "LlmTest".
 */
export interface LlmTest {
  config: LlmRoleData | null
  id: string
  role: 'extractor' | 'checker'
  type: 'llm.test'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "LlmModels".
 */
export interface LlmModels {
  base_url: string | null
  id: string
  provider: string
  type: 'llm.models'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "CheckCancel".
 */
export interface CheckCancel {
  claim_id: string
  id: string
  type: 'check.cancel'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "CheckRetry".
 */
export interface CheckRetry {
  claim_id: string
  id: string
  type: 'check.retry'
}
/**
 * Faz uma busca de teste com as configurações dadas.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SearchTest".
 */
export interface SearchTest {
  id: string
  search: SearchSettingsData
  type: 'search.test'
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
  context: string | null
  context_source: ('user' | 'auto') | null
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
/**
 * Afirmação nova ou com estado alterado. Tem `id` quando responde a claim.manual/discard.
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClaimUpdated".
 */
export interface ClaimUpdated {
  claim: ClaimData
  id: string | null
  type: 'claim.updated'
}
/**
 * Afirmação factual verificável, ancorada num trecho da transcrição (palavras inclusivas).
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClaimData".
 */
export interface ClaimData {
  check: CheckData | null
  context: string | null
  dedup_of: string | null
  end_ms: number
  error: string | null
  from_segment: number
  from_word: number
  id: string
  origin: 'auto' | 'manual'
  session_id: string
  source_text: string
  speaker: string | null
  stage: ('queries' | 'search' | 'reading' | 'analysis') | null
  start_ms: number
  status: 'queued' | 'checking' | 'done' | 'cancelled' | 'discarded' | 'error'
  text: string
  to_segment: number
  to_word: number
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "CheckData".
 */
export interface CheckData {
  checked_at: string
  confidence: number
  duration_ms: number
  justification: string
  model: string | null
  queries: string[]
  search_provider: string | null
  sources: CheckSourceData[]
  verdict: 'verdadeiro' | 'fora_de_contexto' | 'falso' | 'inconclusivo'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "CheckSourceData".
 */
export interface CheckSourceData {
  domain: string
  published: string | null
  quote: string
  stance: 'apoia' | 'refuta' | 'contextualiza'
  tier: 'primary' | 'official' | 'factchecker' | 'press' | 'other'
  title: string
  url: string
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClaimsResult".
 */
export interface ClaimsResult {
  claims: ClaimData[]
  id: string
  session_id: string
  type: 'claims.result'
}
/**
 * Estado do extrator de afirmações de uma sessão (por exemplo, LLM fora do ar).
 *
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ExtractorStatus".
 */
export interface ExtractorStatus {
  message: string | null
  session_id: string
  state: 'idle' | 'running' | 'error' | 'disabled'
  type: 'extractor.status'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SettingsResult".
 */
export interface SettingsResult {
  id: string
  providers: ProviderData[]
  settings: SettingsData
  type: 'settings.result'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ProviderData".
 */
export interface ProviderData {
  default_base_url: string | null
  has_key: boolean
  id: string
  kind: 'llm' | 'search'
  label: string
  needs_key: boolean
  suggested_models: string[]
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "LlmTestResult".
 */
export interface LlmTestResult {
  id: string
  latency_ms: number | null
  message: string | null
  model: string
  ok: boolean
  type: 'llm.test.result'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "LlmModelsResult".
 */
export interface LlmModelsResult {
  id: string
  message: string | null
  models: string[]
  provider: string
  type: 'llm.models.result'
}
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "SearchTestResult".
 */
export interface SearchTestResult {
  id: string
  latency_ms: number | null
  message: string | null
  ok: boolean
  provider: string
  results: number
  type: 'search.test.result'
}
