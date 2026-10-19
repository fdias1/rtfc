// Aceite do M5 (parte de UI): afirmações detectadas viram cards ligados à transcrição;
// descartar, verificar um trecho escolhido, reabrir a sessão e configurar os modelos.

import { expect, test } from '@playwright/test'
import { hasLuciana, launchApp, speechWav, stubOpenDialog } from './helpers'

test.skip(!hasLuciana(), 'gera a fala com a voz Luciana do macOS')

const FALA =
  'A inflação caiu no último trimestre. [[slnc 1300]] Isso é bom. [[slnc 1300]] ' +
  'O desemprego entre os jovens é o maior da história.'

test('afirmações: cards, destaques, descarte, trecho manual e reabertura', async () => {
  test.setTimeout(300_000)
  const wav = speechWav(FALA)
  const first = await launchApp()
  const { win } = first
  await stubOpenDialog(first.app, wav)
  await win.getByTestId('start-file').click()

  // O LLM falso extrai as frases com 4+ palavras ("Isso é bom." fica de fora).
  const cards = win.getByTestId('claim-card')
  await expect(cards).toHaveCount(2, { timeout: 180_000 })
  await expect(cards.first().getByTestId('claim-status')).toHaveText('Na fila')
  await expect(cards.first().getByTestId('claim-text')).toContainText(/infla/i)

  // Cada afirmação aparece sublinhada na transcrição; clicar no trecho foca o card.
  const highlighted = win.locator('[data-claim]')
  await expect(highlighted.first()).toBeVisible()
  await highlighted.last().click()
  await expect(cards.last()).toHaveAttribute('data-focused', 'true')

  // Descartar tira o card e o destaque.
  const discardedId = await cards.first().getAttribute('data-claim-id')
  await cards.first().hover()
  await cards.first().getByTestId('discard-claim').click()
  await expect(cards).toHaveCount(1)
  await expect(win.locator(`[data-claim="${discardedId}"]`)).toHaveCount(0)

  // Selecionar "Isso é bom" e verificar cria uma afirmação manual.
  await expect(win.getByTestId('active-session')).toBeHidden({ timeout: 60_000 })
  await win.evaluate(() => {
    const words = Array.from(document.querySelectorAll('[data-word]')).filter((w) =>
      ['Isso', 'é', 'bom.'].includes(w.textContent ?? '')
    )
    const range = document.createRange()
    range.setStartBefore(words[0]!)
    range.setEndAfter(words[words.length - 1]!)
    window.getSelection()!.removeAllRanges()
    window.getSelection()!.addRange(range)
    document.querySelector('[data-testid=transcript]')!.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }))
  })
  await win.getByTestId('selection-menu').getByRole('button', { name: 'Verificar trecho' }).click()
  await expect(cards).toHaveCount(2)
  const manual = cards.filter({ hasText: 'manual' })
  await expect(manual).toHaveCount(1)
  await expect(manual).toHaveAttribute('data-focused', 'true')
  await expect(win.getByTestId('selection-menu')).toBeHidden()
  await first.app.close()

  // Reabrir o app: a sessão volta com as afirmações (sem a descartada).
  const { app, win: win2 } = await launchApp({ RTFC_SESSIONS_DIR: first.sessionsDir })
  try {
    await win2.getByTestId('tab-sessions').click()
    await win2.getByTestId('session-row').first().click()
    await expect(win2.getByTestId('claim-card')).toHaveCount(2)
    await expect(win2.locator(`[data-claim-id="${discardedId}"]`)).toHaveCount(0)
  } finally {
    await app.close()
  }
})

test('configurações de modelos: testar conexão e salvar', async () => {
  const { app, win } = await launchApp()
  try {
    await win.getByTestId('open-settings').click()
    const extractor = win.getByTestId('role-extractor')
    await expect(extractor).toBeVisible()
    await extractor.getByRole('button', { name: 'Testar conexão' }).click()
    await expect(win.getByTestId('test-result-extractor')).toContainText('OK')

    // Sem chave, um provedor hospedado falha no teste com mensagem clara.
    await win.getByTestId('provider-checker').selectOption('anthropic')
    await win.getByTestId('role-checker').getByRole('button', { name: 'Testar conexão' }).click()
    await expect(win.getByTestId('test-result-checker')).toContainText(/chave/i)
    await expect(win.getByTestId('role-checker')).toContainText('Falta a chave de API')

    await win.getByTestId('model-checker').fill('claude-haiku-5-5')
    await win.getByTestId('save-settings').click()
    await expect(win.getByRole('dialog')).toBeHidden()

    await win.getByTestId('open-settings').click()
    await expect(win.getByTestId('provider-checker')).toHaveValue('anthropic')
    await expect(win.getByTestId('model-checker')).toHaveValue('claude-haiku-5-5')
  } finally {
    await app.close()
  }
})
