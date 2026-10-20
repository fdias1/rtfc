import { existsSync, readFileSync, statSync } from 'node:fs'
import { writeFile } from 'node:fs/promises'
import { basename, extname, join } from 'node:path'
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
import { setupFileLog } from './logger'
import { SidecarManager } from './sidecar'

// Antes do ready.
registerMediaScheme()
enableLoopbackFeatures()

const sessionsDir = process.env.RTFC_SESSIONS_DIR ?? join(app.getPath('documents'), 'rtfc', 'sessions')
const logsDir = join(sessionsDir, '..', 'logs')
const EXPORT_FILTERS: Record<string, string> = {
  md: 'Relatório (Markdown)',
  json: 'Dados completos (JSON)',
  srt: 'Legendas SRT',
  vtt: 'Legendas WebVTT'
}
setupFileLog(logsDir)
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

/** Mesmo formato dos ids gerados pelo backend; impede caminhos como `../`. */
const SESSION_ID_RE = /^\d{8}-\d{6}-(mic|system|file)-[0-9a-f]{4}$/

function sessionDir(sessionId: unknown): string | null {
  if (typeof sessionId !== 'string' || !SESSION_ID_RE.test(sessionId)) return null
  const dir = join(sessionsDir, sessionId)
  return existsSync(join(dir, 'session.json')) ? dir : null
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
  ipcMain.handle(IPC.mediaAllowSession, (_event, sessionId: unknown) => {
    // A lista de arquivos liberados é só da memória; ao reabrir uma sessão de arquivo depois de
    // reiniciar o app, o original é liberado a partir do session.json da própria sessão.
    const dir = sessionDir(sessionId)
    if (!dir) return false
    try {
      const info = JSON.parse(readFileSync(join(dir, 'session.json'), 'utf8')) as { file_path?: string | null }
      if (info.file_path) return allowIfMediaFile(info.file_path) !== null
      return true
    } catch {
      return false
    }
  })
  ipcMain.handle(IPC.appInfo, () => ({ version: app.getVersion(), sessionsDir, logsDir }))
  ipcMain.handle(IPC.appOpenLogs, () => shell.openPath(logsDir).then(() => undefined))
  ipcMain.handle(IPC.appSaveFile, async (event, suggestedName: unknown, content: unknown) => {
    if (typeof suggestedName !== 'string' || typeof content !== 'string') return null
    const ext = extname(suggestedName).slice(1)
    const win = BrowserWindow.fromWebContents(event.sender)
    const options = {
      defaultPath: join(app.getPath('downloads'), basename(suggestedName)),
      filters: ext ? [{ name: EXPORT_FILTERS[ext] ?? ext.toUpperCase(), extensions: [ext] }] : []
    }
    // Testes E2E: grava direto, sem diálogo.
    const forced = process.env.RTFC_TEST_SAVE_DIR
    const result = forced
      ? { canceled: false, filePath: join(forced, basename(suggestedName)) }
      : win
        ? await dialog.showSaveDialog(win, options)
        : await dialog.showSaveDialog(options)
    if (result.canceled || !result.filePath) return null
    await writeFile(result.filePath, content, 'utf8')
    return result.filePath
  })
  ipcMain.handle(IPC.appRevealSession, async (_event, sessionId: unknown) => {
    const dir = sessionDir(sessionId)
    if (dir) await shell.openPath(dir)
  })
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
