// Liga o status do sidecar (vindo do main por IPC) ao cliente WebSocket e ao store.

import type { ServerMessage } from '@rtfc/protocol'
import type { SidecarStatus } from '@shared/ipc'
import { useConnection } from '../store/connection'
import { BackendClient } from './backend-client'

const PING_INTERVAL_MS = 5000

type MessageListener = (msg: ServerMessage) => void
const messageListeners = new Set<MessageListener>()
const closeListeners = new Set<() => void>()

/** Mensagens do servidor que não são respostas a uma requisição (eventos). */
export function onServerMessage(listener: MessageListener): () => void {
  messageListeners.add(listener)
  return () => messageListeners.delete(listener)
}

export function onSocketClose(listener: () => void): () => void {
  closeListeners.add(listener)
  return () => closeListeners.delete(listener)
}

export const backend = new BackendClient({
  onOpen: () => useConnection.getState().setSocket('open'),
  onClose: () => {
    useConnection.getState().setSocket('closed')
    for (const l of closeListeners) l()
  },
  onMessage: (msg) => {
    if (msg.type === 'hello') useConnection.getState().setServerVersion(msg.server_version)
    for (const l of messageListeners) l(msg)
  }
})

function applySidecar(status: SidecarStatus): void {
  useConnection.getState().setSidecar(status)
  if (status.state === 'ready' && status.port && status.token) {
    if (useConnection.getState().socket !== 'open') useConnection.getState().setSocket('connecting')
    backend.connect(status.port, status.token)
  } else {
    backend.disconnect()
    useConnection.getState().setSocket('closed')
  }
}

let started = false

export function startBackendConnection(): void {
  if (started) return
  started = true
  window.rtfc.onSidecarStatus(applySidecar)
  void window.rtfc.getSidecarStatus().then(applySidecar)

  window.setInterval(() => {
    if (useConnection.getState().socket !== 'open') return
    const t0 = performance.now()
    backend
      .request({ type: 'ping' })
      .then(() => useConnection.getState().setLatency(Math.round(performance.now() - t0)))
      .catch(() => undefined)
  }, PING_INTERVAL_MS)
}
