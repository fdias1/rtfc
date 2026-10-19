import { existsSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { BrowserWindow, app, dialog, ipcMain, shell } from 'electron'
import { IPC } from '@shared/ipc'
import { MEDIA_EXTENSIONS } from '@shared/media'
import {
  enableLoopbackFeatures,
  ensureMicrophoneAccess,
  getMediaAccess,
  openPrivacySettings,
  setupCapture
} from './capture'
import { allowMediaDir, allowMediaFile, handleMediaProtocol, registerMediaScheme } from './media-protocol'
import { SidecarManager } from './sidecar'

// Antes do ready.
registerMediaScheme()
enableLoopbackFeatures()

const sessionsDir = process.env.RTFC_SESSIONS_DIR ?? join(app.getPath('documents'), 'rtfc', 'sessions')
const sidecar = new SidecarManager({ sessionsDir })

function createWindow(): BrowserWindow {
  const win = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    show: false,
    title: 'rtfc',
    backgroundColor: '#F7FAFA',
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      sandbox: true,
      contextIsolation: true,
      nodeIntegration: false
    }
  })

  win.once('ready-to-show', () => win.show())

  // Links externos (fontes das checagens) abrem no navegador padrão, nunca dentro do app.
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('https://') || url.startsWith('http://')) void shell.openExternal(url)
    return { action: 'deny' }
  })
  win.webContents.on('will-navigate', (event, url) => {
    if (url !== win.webContents.getURL()) event.preventDefault()
  })

  const devUrl = process.env.ELECTRON_RENDERER_URL
  if (!app.isPackaged && devUrl) {
    void win.loadURL(devUrl)
  } else {
    void win.loadFile(join(__dirname, '../renderer/index.html'))
  }
  return win
}

function allowIfMediaFile(filePath: unknown): string | null {
  if (typeof filePath !== 'string' || !existsSync(filePath) || !statSync(filePath).isFile()) return null
  allowMediaFile(filePath)
  return filePath
}

function registerIpc(): void {
  ipcMain.handle(IPC.sidecarGetStatus, () => sidecar.getStatus())
  ipcMain.handle(IPC.sidecarRestart, () => sidecar.restart())
  sidecar.on('status', (status) => {
    for (const win of BrowserWindow.getAllWindows()) win.webContents.send(IPC.sidecarStatus, status)
  })

  ipcMain.handle(IPC.mediaOpenFile, async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    const options: Electron.OpenDialogOptions = {
      title: 'Abrir áudio ou vídeo',
      properties: ['openFile'],
      filters: [
        { name: 'Áudio e vídeo', extensions: MEDIA_EXTENSIONS },
        { name: 'Todos os arquivos', extensions: ['*'] }
      ]
    }
    const result = win ? await dialog.showOpenDialog(win, options) : await dialog.showOpenDialog(options)
    return result.canceled ? null : allowIfMediaFile(result.filePaths[0])
  })
  ipcMain.handle(IPC.mediaAllowFile, (_event, filePath: unknown) => allowIfMediaFile(filePath))
  ipcMain.handle(IPC.mediaEnsureMic, () => ensureMicrophoneAccess())
  ipcMain.handle(IPC.mediaGetAccess, (_event, kind: 'microphone' | 'screen') => getMediaAccess(kind))
  ipcMain.handle(IPC.mediaOpenPrivacy, (_event, kind: 'microphone' | 'screen') => openPrivacySettings(kind))
}

let quitting = false
app.on('before-quit', (event) => {
  if (quitting) return
  event.preventDefault()
  quitting = true
  void sidecar.stop().finally(() => app.quit())
})

app.on('window-all-closed', () => {
  app.quit()
})

void app.whenReady().then(() => {
  allowMediaDir(sessionsDir)
  handleMediaProtocol()
  setupCapture()
  registerIpc()
  sidecar.start()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})
