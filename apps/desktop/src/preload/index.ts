import { contextBridge, ipcRenderer, webUtils, type IpcRendererEvent } from 'electron'
import { IPC, type AppInfo, type MediaAccess, type RtfcBridge, type SidecarStatus } from '@shared/ipc'

const bridge: RtfcBridge = {
  platform: process.platform,
  getSidecarStatus: () => ipcRenderer.invoke(IPC.sidecarGetStatus) as Promise<SidecarStatus>,
  onSidecarStatus: (listener) => {
    const handler = (_event: IpcRendererEvent, status: SidecarStatus): void => listener(status)
    ipcRenderer.on(IPC.sidecarStatus, handler)
    return () => ipcRenderer.off(IPC.sidecarStatus, handler)
  },
  restartSidecar: () => ipcRenderer.invoke(IPC.sidecarRestart) as Promise<void>,

  openMediaFile: () => ipcRenderer.invoke(IPC.mediaOpenFile) as Promise<string | null>,
  registerDroppedFile: (file) => {
    // Desde o Electron 32 `File.path` não existe mais; o caminho só sai pelo webUtils no preload.
    const path = webUtils.getPathForFile(file)
    return path ? (ipcRenderer.invoke(IPC.mediaAllowFile, path) as Promise<string | null>) : Promise.resolve(null)
  },
  ensureMicrophoneAccess: () => ipcRenderer.invoke(IPC.mediaEnsureMic) as Promise<boolean>,
  getMediaAccess: (kind) => ipcRenderer.invoke(IPC.mediaGetAccess, kind) as Promise<MediaAccess>,
  openPrivacySettings: (kind) => ipcRenderer.invoke(IPC.mediaOpenPrivacy, kind) as Promise<void>,
  allowSessionMedia: (sessionId) => ipcRenderer.invoke(IPC.mediaAllowSession, sessionId) as Promise<boolean>,
  getAppInfo: () => ipcRenderer.invoke(IPC.appInfo) as Promise<AppInfo>,
  revealSession: (sessionId) => ipcRenderer.invoke(IPC.appRevealSession, sessionId) as Promise<void>,
  openLogs: () => ipcRenderer.invoke(IPC.appOpenLogs) as Promise<void>,
  saveTextFile: (suggestedName, content) =>
    ipcRenderer.invoke(IPC.appSaveFile, suggestedName, content) as Promise<string | null>
}

contextBridge.exposeInMainWorld('rtfc', bridge)
