// Tipos e canais IPC compartilhados entre main, preload e renderer.

export type SidecarState = 'starting' | 'ready' | 'restarting' | 'failed' | 'stopped'

export interface SidecarStatus {
  state: SidecarState
  /** Porta e token do backend; presentes apenas quando `state === 'ready'`. */
  port?: number
  token?: string
  pid?: number
  /** Quantas vezes o backend foi reiniciado nesta execução do app. */
  restarts: number
  lastError?: string
}

export const IPC = {
  sidecarGetStatus: 'sidecar:get-status',
  sidecarStatus: 'sidecar:status',
  sidecarRestart: 'sidecar:restart'
} as const

/** API exposta ao renderer pelo preload em `window.rtfc`. */
export interface RtfcBridge {
  getSidecarStatus(): Promise<SidecarStatus>
  onSidecarStatus(listener: (status: SidecarStatus) => void): () => void
  restartSidecar(): Promise<void>
}
