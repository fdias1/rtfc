import { execFileSync, spawnSync } from 'node:child_process'
import { mkdtempSync, readdirSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { _electron as electron, expect, type ElectronApplication, type Page } from '@playwright/test'

export interface Launched {
  app: ElectronApplication
  win: Page
  sessionsDir: string
}

/** Mídia falsa, o menor modelo de STT (pré-carregado ao abrir) e LLM falso. */
export const TEST_ENV = {
  RTFC_FAKE_MEDIA: '1',
  RTFC_STT_ENGINE: 'faster-whisper',
  RTFC_STT_MODEL: 'tiny',
  // LLM determinístico (sem rede nem Ollama): cada frase com 4+ palavras vira uma afirmação.
  RTFC_TEST_FAKE_LLM: '1',
  // Falantes sem baixar o modelo de voz: alterna entre dois a cada frase.
  RTFC_DIARIZER: 'fake'
}

export async function launchApp(extraEnv: Record<string, string> = {}): Promise<Launched> {
  // Reusar a pasta (RTFC_SESSIONS_DIR em extraEnv) simula reabrir o app com sessões salvas.
  // A pasta-mãe guarda settings.json e rtfc.sqlite: precisa ser exclusiva de cada teste.
  const sessionsDir = extraEnv.RTFC_SESSIONS_DIR ?? join(mkdtempSync(join(tmpdir(), 'rtfc-e2e-')), 'sessions')
  const app = await electron.launch({
    args: [resolve(__dirname, '..')],
    env: { ...process.env, ...TEST_ENV, RTFC_SESSIONS_DIR: sessionsDir, ...extraEnv } as Record<string, string>
  })
  const win = await app.firstWindow()
  win.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning')
      console.log(`[renderer ${m.type()}] ${m.text().replace(/token=[^&\s'"]+/g, 'token=***')}`)
  })
  win.on('pageerror', (e) => console.log(`[renderer pageerror] ${e.message}`))
  await expect(win.getByTestId('connection-status')).toHaveAttribute('data-state', 'connected', {
    timeout: 45_000
  })
  return { app, win, sessionsDir }
}

export function mediaDuration(path: string): number {
  return Number(
    execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', path], {
      encoding: 'utf8'
    }).trim()
  )
}

/** Volume máximo (dBFS) do arquivo, via filtro volumedetect do ffmpeg (que escreve no stderr). */
export function maxVolumeDb(path: string): number {
  const { stderr } = spawnSync('ffmpeg', ['-hide_banner', '-i', path, '-af', 'volumedetect', '-f', 'null', '-'], {
    encoding: 'utf8'
  })
  const m = /max_volume:\s*(-?[\d.]+) dB/.exec(stderr)
  if (!m) throw new Error(`volumedetect falhou: ${stderr}`)
  return Number(m[1])
}

export function onlySessionDir(sessionsDir: string): string {
  const dirs = readdirSync(sessionsDir)
  expect(dirs).toHaveLength(1)
  return join(sessionsDir, dirs[0]!)
}

/** Fala pt-BR gerada com a voz Luciana do macOS (WAV 48 kHz mono, com silêncio nas pontas). */
export function speechWav(text: string): string {
  const dir = mkdtempSync(join(tmpdir(), 'rtfc-fala-'))
  const aiff = join(dir, 'fala.aiff')
  const wav = join(dir, 'fala.wav')
  execFileSync('say', ['-v', 'Luciana', '-o', aiff, text])
  execFileSync('ffmpeg', [
    '-v',
    'error',
    '-i',
    aiff,
    '-af',
    'adelay=1000,apad=pad_dur=2',
    '-ar',
    '48000',
    '-ac',
    '1',
    wav
  ])
  return wav
}

export function hasLuciana(): boolean {
  if (process.platform !== 'darwin') return false
  try {
    return execFileSync('say', ['-v', '?'], { encoding: 'utf8' }).includes('Luciana')
  } catch {
    return false
  }
}

/** Faz o seletor de arquivos devolver `path` (sem diálogo nativo no teste). */
export async function stubOpenDialog(app: ElectronApplication, path: string): Promise<void> {
  await app.evaluate(({ dialog }, p) => {
    dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: [p] })) as typeof dialog.showOpenDialog
  }, path)
}
