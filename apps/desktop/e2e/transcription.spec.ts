// Aceite do M2 (parte automatizável): transcrição de arquivo e ao vivo com o modelo tiny.
// Precisa do `say` do macOS para gerar a fala de teste; pulado em outros SOs.

import { execFileSync } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { launchApp, onlySessionDir } from './helpers'

const FRASE = 'Boa noite a todos. Hoje eu quero falar sobre a educação pública no nosso país.'

function hasLuciana(): boolean {
  if (process.platform !== 'darwin') return false
  try {
    return execFileSync('say', ['-v', '?'], { encoding: 'utf8' }).includes('Luciana')
  } catch {
    return false
  }
}

test.skip(!hasLuciana(), 'gera a fala com a voz Luciana do macOS')

// O helper já usa o modelo tiny (~75 MB, fica no cache do Hugging Face).
const STT_ENV = {}

function speechWav(): string {
  const dir = mkdtempSync(join(tmpdir(), 'rtfc-fala-'))
  const aiff = join(dir, 'fala.aiff')
  const wav = join(dir, 'fala.wav')
  execFileSync('say', ['-v', 'Luciana', '-o', aiff, FRASE])
  // 1 s de silêncio antes e 2 s depois, 48 kHz (o que o Chromium espera do arquivo de microfone falso).
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

test('arquivo de áudio é transcrito e gera SRT', async () => {
  test.setTimeout(240_000)
  const wav = speechWav()
  const { app, win, sessionsDir } = await launchApp(STT_ENV)
  try {
    await app.evaluate(({ dialog }, path) => {
      dialog.showOpenDialog = (async () => ({ canceled: false, filePaths: [path] })) as typeof dialog.showOpenDialog
    }, wav)
    await win.getByTestId('start-file').click()
    await expect(win.getByTestId('active-session')).toBeHidden({ timeout: 180_000 })
    await expect(win.getByTestId('transcript-segment').first()).toBeVisible()
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
  const wav = speechWav()
  const { app, win, sessionsDir } = await launchApp({ ...STT_ENV, RTFC_FAKE_MIC_WAV: wav })
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
