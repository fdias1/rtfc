import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron'
import { IPC, type RtfcBridge, type SidecarStatus } from '@shared/ipc'

const bridge: RtfcBridge = {
  getSidecarStatus: () => ipcRenderer.invoke(IPC.sidecarGetStatus) as Promise<SidecarStatus>,
  onSidecarStatus: (listener) => {
    const handler = (_event: IpcRendererEvent, status: SidecarStatus): void => listener(status)
    ipcRenderer.on(IPC.sidecarStatus, handler)
    return () => ipcRenderer.off(IPC.sidecarStatus, handler)
  },
  restartSidecar: () => ipcRenderer.invoke(IPC.sidecarRestart) as Promise<void>
}

contextBridge.exposeInMainWorld('rtfc', bridge)
