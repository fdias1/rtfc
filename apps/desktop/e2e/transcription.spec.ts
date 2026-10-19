// Aceite do M2 (parte automatizável): transcrição de arquivo e ao vivo com o modelo tiny.
// Precisa do `say` do macOS para gerar a fala de teste; pulado em outros SOs.

import { existsSync, readFileSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { hasLuciana, launchApp, onlySessionDir, speechWav, stubOpenDialog } from './helpers'

const FRASE = 'Boa noite a todos. Hoje eu quero falar sobre a educação pública no nosso país.'

test.skip(!hasLuciana(), 'gera a fala com a voz Luciana do macOS')

test('arquivo de áudio é transcrito e gera SRT', async () => {
  test.setTimeout(240_000)
  const wav = speechWav(FRASE)
  const { app, win, sessionsDir } = await launchApp()
  try {
    await stubOpenDialog(app, wav)
    await win.getByTestId('start-file').click()
    await expect(win.getByTestId('transcript-segment').first()).toBeVisible({ timeout: 180_000 })
    await expect(win.getByTestId('active-session')).toBeHidden({ timeout: 60_000 })
    await expect(win.getByTestId('transcript')).toContainText(/noite/i)

    const srt = readFileSync(join(onlySessionDir(sessionsDir), 'transcricao.srt'), 'utf8')
    expect(srt).toMatch(/^1\n00:00:0\d,\d{3} --> 00:00:\d{2},\d{3}\n/)
    expect(srt.toLowerCase()).toContain('noite')
  } finally {
    await app.close()
  }
})

test('microfone ao vivo é transcrito com latência dentro da meta', async () => {
  test.setTimeout(240_000)
  const wav = speechWav(FRASE)
  const { app, win, sessionsDir } = await launchApp({ RTFC_FAKE_MIC_WAV: wav })
  try {
    await expect(win.getByTestId('stt-status')).toHaveAttribute('data-state', 'ready', { timeout: 180_000 })
    await win.getByTestId('start-mic').click()
    // O arquivo do microfone falso toca em loop: a primeira frase chega em segundos.
    await expect(win.getByTestId('transcript')).toContainText(/noite/i, { timeout: 30_000 })
    await expect(win.getByTestId('latency')).toBeVisible({ timeout: 30_000 })
    const latency = Number((await win.getByTestId('latency').textContent())?.match(/[\d.]+/)?.[0])
    expect(latency).toBeLessThanOrEqual(3)
    await win.getByTestId('stop-session').click()
    await expect(win.getByTestId('active-session')).toBeHidden()

    const dir = onlySessionDir(sessionsDir)
    expect(existsSync(join(dir, 'transcricao.vtt'))).toBe(true)
    expect(readFileSync(join(dir, 'transcricao.vtt'), 'utf8')).toMatch(/^WEBVTT\n\n00:00:/)
  } finally {
    await app.close()
  }
})
