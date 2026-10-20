// Aceite do M1 (parte automatizável): microfone (falso) → audio.ogg, arquivo → player,
// e app morto à força mantém a gravação.

import { execFileSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { hasLuciana, launchApp, maxVolumeDb, mediaDuration, onlySessionDir, speechWav } from './helpers'

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

test('dá para iniciar uma nova sessão ao vivo depois de encerrar a anterior', async () => {
  // Regressão: a 2ª sessão ao vivo na mesma janela era recusada ("já existe uma sessão ao vivo").
  const { app, win } = await launchApp()
  try {
    for (let i = 0; i < 3; i++) {
      await win.getByTestId('start-mic').click()
      await expect(win.getByTestId('active-session')).toBeVisible({ timeout: 15_000 })
      await expect(win.getByTestId('session-elapsed')).toHaveText(/00:0[1-9]/, { timeout: 15_000 })
      await win.getByTestId('stop-session').click()
      await expect(win.getByTestId('active-session')).toBeHidden()
    }
    await expect(win.getByRole('alert')).toHaveCount(0)
  } finally {
    await app.close()
  }
})

test('crash do backend no meio: a sessão reabre interrompida, com áudio e transcrição', async () => {
  test.skip(!hasLuciana(), 'gera a fala com a voz Luciana do macOS')
  test.setTimeout(180_000)
  const wav = speechWav('Boa noite a todos. Hoje eu quero falar sobre a educação pública no nosso país.')
  const first = await launchApp({ RTFC_FAKE_MIC_WAV: wav })
  await expect(first.win.getByTestId('stt-status')).toHaveAttribute('data-state', 'ready', { timeout: 120_000 })
  await first.win.getByTestId('start-mic').click()
  await expect(first.win.getByTestId('transcript-segment').first()).toBeVisible({ timeout: 30_000 })

  // Simula um crash de verdade: o backend morre sem finalizar nada, e o app junto.
  const { pid } = await first.win.evaluate(() => window.rtfc.getSidecarStatus())
  process.kill(pid!, 'SIGKILL')
  process.kill(first.app.process().pid!, 'SIGKILL')
  const dir = onlySessionDir(first.sessionsDir)
  expect(JSON.parse(readFileSync(join(dir, 'session.json'), 'utf8')).status).toBe('recording')

  const { app, win } = await launchApp({ RTFC_SESSIONS_DIR: first.sessionsDir })
  try {
    await win.getByTestId('tab-sessions').click()
    const row = win.getByTestId('session-row').first()
    await expect(row).toContainText('interrompida')
    await row.click()
    await expect(win.getByTestId('transcript-segment').first()).toBeVisible()
    await expect(win.getByTestId('transcript')).toContainText(/noite/i)
    const audio = win.locator('[data-testid=media-player] audio')
    await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => a.duration), { timeout: 10_000 }).toBeGreaterThan(2)
    const info = JSON.parse(readFileSync(join(dir, 'session.json'), 'utf8'))
    expect(info.status).toBe('interrupted')
    expect(info.duration_ms).toBeGreaterThan(2000)
    expect(readFileSync(join(dir, 'transcricao.vtt'), 'utf8')).toMatch(/noite/i)
  } finally {
    await app.close()
  }
})
