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

export async function launchApp(extraEnv: Record<string, string> = {}): Promise<Launched> {
  const sessionsDir = mkdtempSync(join(tmpdir(), 'rtfc-e2e-'))
  const app = await electron.launch({
    args: [resolve(__dirname, '..')],
    env: { ...process.env, RTFC_SESSIONS_DIR: sessionsDir, RTFC_FAKE_MEDIA: '1', ...extraEnv } as Record<string, string>
  })
  const win = await app.firstWindow()
  win.on('console', (m) => {
    if (m.type() === 'error' || m.type() === 'warning') console.log(`[renderer ${m.type()}] ${m.text()}`)
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
