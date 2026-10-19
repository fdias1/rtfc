import { create } from 'zustand'
import type { SidecarStatus } from '@shared/ipc'

export type SocketState = 'idle' | 'connecting' | 'open' | 'closed'

interface ConnectionState {
  sidecar: SidecarStatus
  socket: SocketState
  serverVersion?: string
  latencyMs?: number
  setSidecar(status: SidecarStatus): void
  setSocket(state: SocketState): void
  setServerVersion(version: string): void
  setLatency(ms: number): void
}

export const useConnection = create<ConnectionState>((set) => ({
  sidecar: { state: 'starting', restarts: 0 },
  socket: 'idle',
  setSidecar: (sidecar) => set({ sidecar }),
  setSocket: (socket) => set(socket === 'open' ? { socket } : { socket, latencyMs: undefined }),
  setServerVersion: (serverVersion) => set({ serverVersion }),
  setLatency: (latencyMs) => set({ latencyMs })
}))

export type ConnectionSummary = 'connected' | 'connecting' | 'failed'

export function summarize(sidecar: SidecarStatus, socket: SocketState): ConnectionSummary {
  if (sidecar.state === 'failed') return 'failed'
  if (sidecar.state === 'ready' && socket === 'open') return 'connected'
  return 'connecting'
}
