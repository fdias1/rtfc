// Aceite do M1 (parte automatizável): microfone (falso) → audio.ogg, arquivo → player,
// e app morto à força mantém a gravação.

import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { launchApp, maxVolumeDb, mediaDuration, onlySessionDir } from './helpers'

test('microfone grava audio.ogg e mostra o player ao encerrar', async () => {
  const { app, win, sessionsDir } = await launchApp()
  try {
    await win.getByTestId('start-mic').click()
    await expect(win.getByTestId('active-session')).toBeVisible({ timeout: 15_000 })
    await expect(win.getByTestId('session-elapsed')).toHaveText(/00:0[3-9]/, { timeout: 15_000 })
    await win.getByTestId('stop-session').click()
    await expect(win.getByTestId('active-session')).toBeHidden()
    await expect(win.getByTestId('media-player').locator('audio')).toBeVisible()

    // O player carrega a gravação pelo protocolo rtfc-media (com Range).
    await expect
      .poll(() => win.locator('audio').evaluate((a: HTMLAudioElement) => a.readyState), { timeout: 10_000 })
      .toBeGreaterThanOrEqual(1)

    const dir = onlySessionDir(sessionsDir)
    expect(mediaDuration(join(dir, 'audio.ogg'))).toBeGreaterThan(2.5)
    // O microfone falso do Chromium gera bipes: a gravação não pode ser silêncio.
    expect(maxVolumeDb(join(dir, 'audio.ogg'))).toBeGreaterThan(-20)
    const info = JSON.parse(readFileSync(join(dir, 'session.json'), 'utf8'))
    expect(info.status).toBe('completed')
    expect(info.source).toBe('mic')
  } finally {
    await app.close()
  }
})

test('arquivo de vídeo abre no player e é processado', async () => {
  const { app, win, sessionsDir } = await launchApp()
  const video = join(sessionsDir, '..', `rtfc-e2e-video-${Date.now()}.mp4`)
  execFileSync('ffmpeg', [
    ...['-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:d=3'],
    ...['-f', 'lavfi', '-i', 'sine=duration=3', '-shortest', '-pix_fmt', 'yuv420p', video]
  ])
  try {
    // Sem diálogo nativo no teste: o seletor devolve o arquivo gerado.
    await app.evaluate(({ dialog }, path) => {
      dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: [path] })) as typeof dialog.showOpenDialog
    }, video)
    await win.getByTestId('start-file').click()
    await expect(win.getByTestId('media-player').locator('video')).toBeVisible({ timeout: 15_000 })
    await expect(win.getByTestId('active-session')).toBeHidden({ timeout: 15_000 })
    await expect
      .poll(() => win.locator('video').evaluate((v: HTMLVideoElement) => v.readyState), { timeout: 10_000 })
      .toBeGreaterThanOrEqual(1)
    const info = JSON.parse(readFileSync(join(onlySessionDir(sessionsDir), 'session.json'), 'utf8'))
    expect(info.status).toBe('completed')
    expect(info.media_kind).toBe('video')
    // O AAC adiciona alguns ms de priming.
    expect(info.duration_ms).toBeGreaterThanOrEqual(2950)
    expect(info.duration_ms).toBeLessThanOrEqual(3100)
  } finally {
    await app.close()
  }
})

test('matar o app no meio da gravação mantém o áudio gravado', async () => {
  const { app, win, sessionsDir } = await launchApp()
  await win.getByTestId('start-mic').click()
  await expect(win.getByTestId('session-elapsed')).toHaveText(/00:0[4-9]/, { timeout: 15_000 })

  const pid = app.process().pid!
  process.kill(pid, 'SIGKILL')

  // Sem o Electron, o stdin do backend fecha: ele finaliza a sessão e sai.
  const dir = onlySessionDir(sessionsDir)
  await expect
    .poll(() => JSON.parse(readFileSync(join(dir, 'session.json'), 'utf8')).status, { timeout: 15_000 })
    .toBe('completed')
  expect(mediaDuration(join(dir, 'audio.ogg'))).toBeGreaterThan(3)
})
