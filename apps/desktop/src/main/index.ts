import { join } from 'node:path'
import { BrowserWindow, app, ipcMain, shell } from 'electron'
import { IPC } from '@shared/ipc'
import { SidecarManager } from './sidecar'

const sidecar = new SidecarManager()

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

function registerIpc(): void {
  ipcMain.handle(IPC.sidecarGetStatus, () => sidecar.getStatus())
  ipcMain.handle(IPC.sidecarRestart, () => sidecar.restart())
  sidecar.on('status', (status) => {
    for (const win of BrowserWindow.getAllWindows()) win.webContents.send(IPC.sidecarStatus, status)
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
  registerIpc()
  sidecar.start()
  createWindow()
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow()
  })
})
