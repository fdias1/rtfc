// Liga o status do sidecar (vindo do main por IPC) ao cliente WebSocket e ao store.

import type { SidecarStatus } from '@shared/ipc'
import { useConnection } from '../store/connection'
import { BackendClient } from './backend-client'

const PING_INTERVAL_MS = 5000

export const backend = new BackendClient({
  onOpen: () => useConnection.getState().setSocket('open'),
  onClose: () => useConnection.getState().setSocket('closed'),
  onMessage: (msg) => {
    if (msg.type === 'hello') useConnection.getState().setServerVersion(msg.server_version)
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
