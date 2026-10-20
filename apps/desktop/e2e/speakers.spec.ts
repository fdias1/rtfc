// M4: falantes na transcrição, renomear (refletido no VTT) e refinar a sessão salva.
// Com RTFC_DIARIZER=fake, as frases alternam entre dois falantes.

import { mkdtempSync, readFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { expect, test } from '@playwright/test'
import { hasLuciana, launchApp, onlySessionDir, speechWav, stubOpenDialog } from './helpers'

// A pausa de 1,5 s ([[slnc]] do `say`) garante dois segmentos mesmo com o modelo tiny.
const FALA = 'Boa noite a todos. [[slnc 1500]] O desemprego caiu no último ano, segundo o IBGE.'

test.skip(!hasLuciana(), 'gera a fala com a voz Luciana do macOS')

test('falantes aparecem, são renomeados no VTT e refinados', async () => {
  test.setTimeout(240_000)
  const wav = speechWav(FALA)
  const saveDir = mkdtempSync(join(tmpdir(), 'rtfc-export-'))
  const { app, win, sessionsDir } = await launchApp({ RTFC_TEST_SAVE_DIR: saveDir })
  try {
    await stubOpenDialog(app, wav)
    await win.getByTestId('start-file').click()
    await expect(win.getByTestId('transcript-segment').first()).toBeVisible({ timeout: 180_000 })
    await expect(win.getByTestId('active-session')).toBeHidden({ timeout: 60_000 })

    const chips = win.getByTestId('speaker-chip')
    await expect(chips).toHaveCount(2)
    await expect(chips.first()).toHaveText('Falante 1')
    await expect(win.getByTestId('segment-speaker').first()).toHaveText('Falante 1')

    await chips.first().click()
    await win.getByTestId('speaker-name-input').fill('Apresentadora')
    await win.getByTestId('speaker-name-input').press('Enter')
    await expect(win.getByTestId('segment-speaker').first()).toHaveText('Apresentadora')
    await expect(win.getByTestId('claim-speaker').first()).toContainText(/Apresentadora|Falante 2/)

    const dir = onlySessionDir(sessionsDir)
    await expect.poll(() => readFileSync(join(dir, 'transcricao.vtt'), 'utf8')).toContain('<v Apresentadora>')
    expect(readFileSync(join(dir, 'transcricao.vtt'), 'utf8')).toContain('<v Falante 2>')

    await win.getByTestId('refine-speakers').click()
    await expect(win.getByTestId('refine-speakers')).toHaveText('Refinar falantes', { timeout: 60_000 })
    // O nome dado sobrevive ao refinamento.
    await expect(win.getByTestId('speaker-chip').first()).toHaveText('Apresentadora')

    // Exportar: relatório e legendas levam os nomes dos falantes (M7).
    await win.getByTestId('export-button').click()
    await win.getByTestId('export-md').click()
    await expect(win.getByTestId('export-message')).toContainText('Salvo em')
    const saved = (await win.getByTestId('export-message').getAttribute('title'))!.replace('Salvo em ', '')
    const md = readFileSync(saved, 'utf8')
    expect(md).toMatch(/^# fala\.wav\n/)
    expect(md).toContain('## Afirmações')
    expect(md).toContain('**[00:0')
    expect(md).toContain('Apresentadora:**')
    await win.getByTestId('export-button').click()
    await win.getByTestId('export-srt').click()
    await expect(win.getByTestId('export-message')).toContainText('.srt')
    const srtPath = (await win.getByTestId('export-message').getAttribute('title'))!.replace('Salvo em ', '')
    expect(readFileSync(srtPath, 'utf8')).toMatch(/^1\n00:00:\d\d,\d{3} --> .*\nApresentadora: /)
  } finally {
    await app.close()
  }
})
