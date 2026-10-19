/* eslint-disable */
// GERADO por packages/protocol/scripts/gen.mjs a partir de backend/src/rtfc/protocol.
// Não edite à mão: rode `pnpm protocol:gen`.

/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ClientMessage".
 */
export type ClientMessage = Ping | EchoRequest
/**
 * This interface was referenced by `RtfcProtocol`'s JSON-Schema
 * via the `definition` "ServerMessage".
 */
export type ServerMessage = Hello | Pong | EchoReply | ErrorMessage

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
