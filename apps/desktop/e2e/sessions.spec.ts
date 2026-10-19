// Aceite do M3: reabrir uma sessão salva, clicar numa frase e ouvir o ponto exato;
// selecionar um trecho mostra o menu de ação ("Verificar trecho"); renomear e apagar.

import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { hasLuciana, launchApp, onlySessionDir, speechWav, stubOpenDialog } from './helpers'

test.skip(!hasLuciana(), 'gera a fala com a voz Luciana do macOS')

// Pausas de 1,3 s entre as frases: separam os segmentos mesmo que o modelo tiny troque o
// ponto final por vírgula.
const FALA =
  'Boa noite a todos. [[slnc 1300]] Hoje eu quero falar sobre a educação pública no nosso país. [[slnc 1300]] ' +
  'Durante muito tempo, as escolas do interior ficaram esquecidas pelo governo federal.'

test('sessão salva reabre com player sincronizado, seleção, renomear e apagar', async () => {
  test.setTimeout(300_000)
  const wav = speechWav(FALA)

  // 1ª execução do app: cria a sessão a partir de um arquivo.
  const first = await launchApp()
  const sessionsDir = first.sessionsDir
  await stubOpenDialog(first.app, wav)
  await first.win.getByTestId('start-file').click()
  // Espera a sessão começar e terminar (toBeHidden sozinho passaria antes de ela aparecer).
  await expect(first.win.getByTestId('transcript-segment')).toHaveCount(3, { timeout: 180_000 })
  await expect(first.win.getByTestId('active-session')).toBeHidden({ timeout: 60_000 })
  await first.app.close()

  // 2ª execução: reabre pelo histórico.
  const { app, win } = await launchApp({ RTFC_SESSIONS_DIR: sessionsDir })
  try {
    await win.getByTestId('tab-sessions').click()
    await win.getByTestId('session-row').first().click()
    await expect(win.getByTestId('transcript-segment')).toHaveCount(3)
    await expect(win.getByTestId('shown-title')).toHaveText('fala.wav')
    const audio = win.locator('[data-testid=media-player] audio')
    await expect
      .poll(() => audio.evaluate((a: HTMLAudioElement) => a.readyState), { timeout: 10_000 })
      .toBeGreaterThan(0)

    // Clicar no horário da 3ª frase toca o áudio a partir dela.
    const third = win.getByTestId('transcript-segment').nth(2)
    const label = (await third.getByTestId('segment-time').textContent())!
    const [mm, ss] = label.split(':').map(Number)
    await third.getByTestId('segment-time').click()
    await expect.poll(() => audio.evaluate((a: HTMLAudioElement) => !a.paused)).toBe(true)
    const t = await audio.evaluate((a: HTMLAudioElement) => a.currentTime)
    expect(t).toBeGreaterThanOrEqual(mm! * 60 + ss! - 0.1)
    expect(t).toBeLessThan(mm! * 60 + ss! + 2)
    // A frase tocando fica destacada.
    await expect(third).toHaveAttribute('data-active', 'true', { timeout: 5_000 })
    await audio.evaluate((a: HTMLAudioElement) => a.pause())

    // Selecionar palavras da 2ª frase mostra o menu de ação.
    await win.evaluate(() => {
      const words = document.querySelectorAll('[data-seg="1"][data-word]')
      const range = document.createRange()
      range.setStartBefore(words[1]!)
      range.setEndAfter(words[4]!)
      const sel = window.getSelection()!
      sel.removeAllRanges()
      sel.addRange(range)
      document.querySelector('[data-testid=transcript]')!.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
    })
    const menu = win.getByTestId('selection-menu')
    await expect(menu).toBeVisible()
    await expect(menu.getByRole('button', { name: 'Verificar trecho' })).toBeEnabled()

    // Renomear.
    await win.getByTestId('session-row').first().hover()
    await win.getByTestId('rename-session').click()
    await win.getByTestId('rename-input').fill('Discurso de teste')
    await win.getByTestId('rename-input').press('Enter')
    await expect(win.getByTestId('shown-title')).toHaveText('Discurso de teste')
    await expect(win.getByTestId('session-row').first()).toContainText('Discurso de teste')

    // Apagar (com confirmação) remove a pasta, mas não o arquivo original.
    const dir = onlySessionDir(sessionsDir)
    await win.getByTestId('session-row').first().hover()
    await win.getByTestId('delete-session').click()
    await win.getByTestId('confirm-delete').click()
    await expect(win.getByTestId('session-row')).toHaveCount(0)
    expect(existsSync(dir)).toBe(false)
    expect(existsSync(wav)).toBe(true)
    expect(existsSync(join(sessionsDir, '..', 'rtfc.sqlite'))).toBe(true)
  } finally {
    await app.close()
  }
})
