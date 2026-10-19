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

export type MediaAccess = 'granted' | 'denied' | 'not-determined' | 'restricted' | 'unknown'

export const IPC = {
  sidecarGetStatus: 'sidecar:get-status',
  sidecarStatus: 'sidecar:status',
  sidecarRestart: 'sidecar:restart',
  mediaOpenFile: 'media:open-file',
  mediaAllowFile: 'media:allow-file',
  mediaEnsureMic: 'media:ensure-mic',
  mediaGetAccess: 'media:get-access',
  mediaOpenPrivacy: 'media:open-privacy'
} as const

/** API exposta ao renderer pelo preload em `window.rtfc`. */
export interface RtfcBridge {
  platform: string
  getSidecarStatus(): Promise<SidecarStatus>
  onSidecarStatus(listener: (status: SidecarStatus) => void): () => void
  restartSidecar(): Promise<void>

  /** Abre o seletor de arquivos de áudio/vídeo. Devolve o caminho (já liberado para o player) ou null. */
  openMediaFile(): Promise<string | null>
  /** Caminho de um arquivo arrastado para a janela (liberado para o player), ou null se inválido. */
  registerDroppedFile(file: File): Promise<string | null>
  /** No macOS pede acesso ao microfone se ainda não decidido. */
  ensureMicrophoneAccess(): Promise<boolean>
  getMediaAccess(kind: 'microphone' | 'screen'): Promise<MediaAccess>
  openPrivacySettings(kind: 'microphone' | 'screen'): Promise<void>
}
