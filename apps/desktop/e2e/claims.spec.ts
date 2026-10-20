// Aceite do M5/M6 (UI): afirmações detectadas viram cards ligados à transcrição e são
// checadas automaticamente (veredicto + fontes); descartar, rechecar, verificar um trecho
// escolhido, filtrar, reabrir a sessão e configurar modelos e busca.

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
  await expect(cards.first().getByTestId('claim-text')).toContainText(/infla/i)

  // A checagem roda sozinha: veredicto, justificativa e fontes (LLM e busca falsos).
  await expect(cards.first().getByTestId('claim-status')).toHaveAttribute('data-verdict', 'verdadeiro', {
    timeout: 30_000
  })
  await expect(cards.first().getByTestId('check-justification')).toContainText('fontes de teste')
  const sources = cards.first().getByTestId('check-sources').locator('li')
  await expect(sources).toHaveCount(2)
  // Fonte primária primeiro (ADR 0006), depois a agência de checagem.
  await expect(sources.first()).toContainText('ibge.gov.br')
  await expect(sources.first()).toContainText('fonte primária')
  await expect(sources.nth(1)).toContainText('aosfatos.org')
  // O sublinhado na transcrição ganha a cor do veredicto.
  await expect(win.locator('[data-verdict="verdadeiro"]').first()).toBeVisible()

  // Filtro por veredicto.
  await win.getByTestId('filter-verdadeiro').click()
  await expect(cards).toHaveCount(2)
  await win.getByTestId('filter-verdadeiro').click()

  // Rechecar volta para a fila e termina de novo.
  await cards.first().hover()
  const checkedAt = async (): Promise<string | null> =>
    (await cards.first().getByTestId('check-result').getAttribute('data-checked-at')) ?? null
  const before = await checkedAt()
  await cards.first().getByTestId('retry-check').click()
  // Só segue quando o resultado novo chegou (o veredicto anterior fica na tela até lá).
  await expect.poll(checkedAt, { timeout: 30_000 }).not.toBe(before)
  await expect(cards.first().getByTestId('claim-status')).toHaveAttribute('data-verdict', 'verdadeiro')

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
  // O pedido manual também é checado.
  await expect(manual.getByTestId('claim-status')).toHaveAttribute('data-verdict', 'verdadeiro', {
    timeout: 30_000
  })
  await expect(win.getByTestId('selection-menu')).toBeHidden()
  await first.app.close()

  // Reabrir o app: a sessão volta com as afirmações (sem a descartada).
  const { app, win: win2 } = await launchApp({ RTFC_SESSIONS_DIR: first.sessionsDir })
  try {
    await win2.getByTestId('tab-sessions').click()
    await win2.getByTestId('session-row').first().click()
    await expect(win2.getByTestId('claim-card')).toHaveCount(2)
    await expect(win2.locator(`[data-claim-id="${discardedId}"]`)).toHaveCount(0)
    // Os resultados das checagens também voltam.
    await expect(win2.getByTestId('check-result')).toHaveCount(2)
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
    await expect(win.getByTestId('test-result-extractor')).toContainText('OK', { timeout: 15_000 })

    // Sem chave, um provedor hospedado falha no teste com mensagem clara.
    await win.getByTestId('provider-checker').selectOption('anthropic')
    await win.getByTestId('role-checker').getByRole('button', { name: 'Testar conexão' }).click()
    await expect(win.getByTestId('test-result-checker')).toContainText(/chave/i, { timeout: 15_000 })
    await expect(win.getByTestId('role-checker')).toContainText('Falta a chave de API')

    // Teste de busca (provedor falso no modo de teste).
    await win.getByTestId('search-settings').getByRole('button', { name: 'Testar busca' }).click()
    await expect(win.getByTestId('search-test-result')).toContainText('OK', { timeout: 15_000 })

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

test('contexto do conteúdo: definido antes, editado e gerado pela transcrição', async () => {
  test.setTimeout(240_000)
  const wav = speechWav(FALA)
  const { app, win } = await launchApp()
  try {
    await win.getByTestId('context-draft').fill('Discurso de teste sobre economia, Brasil, 2026.')
    await stubOpenDialog(app, wav)
    await win.getByTestId('start-file').click()
    const bar = win.getByTestId('context-bar')
    await expect(bar.getByTestId('context-text')).toHaveText('Discurso de teste sobre economia, Brasil, 2026.')
    await expect(bar).toContainText('definido por você')
    await expect(win.getByTestId('claim-card').first()).toBeVisible({ timeout: 180_000 })
    // O contexto da afirmação (do extrator) aparece no card.
    await expect(win.getByTestId('claim-context').first()).toHaveText('Contexto de teste.')

    await bar.getByTestId('edit-context').click()
    await bar.getByTestId('context-input').fill('Outro contexto.')
    await bar.getByTestId('save-context').click()
    await expect(bar.getByTestId('context-text')).toHaveText('Outro contexto.')

    await bar.getByTestId('generate-context').click()
    await expect(bar.getByTestId('context-text')).toHaveText('Conteúdo de teste gerado automaticamente.')
    await expect(bar).toContainText('gerado automaticamente')
  } finally {
    await app.close()
  }
})

test('rechecagem com modelo de qualidade: progresso, "mudou" e filtro', async () => {
  test.setTimeout(240_000)
  const wav = speechWav(FALA)
  const { app, win } = await launchApp()
  try {
    await stubOpenDialog(app, wav)
    await win.getByTestId('start-file').click()
    const cards = win.getByTestId('claim-card')
    await expect(cards).toHaveCount(2, { timeout: 180_000 })
    await expect(win.getByTestId('active-session')).toBeHidden({ timeout: 60_000 })
    for (const card of await cards.all()) {
      await expect(card.getByTestId('claim-status')).toHaveAttribute('data-verdict', 'verdadeiro', { timeout: 30_000 })
    }

    // O revisor falso discorda do checador rápido: tudo vira "falso" e aparece o "mudou".
    await expect(win.getByTestId('start-review')).toContainText('fake-review')
    await win.getByTestId('start-review').click()
    await expect(win.getByTestId('review-done')).toContainText('2/2', { timeout: 60_000 })
    for (const card of await cards.all()) {
      await expect(card.getByTestId('claim-status')).toHaveAttribute('data-verdict', 'falso')
      await expect(card.getByTestId('review-chip')).toHaveAttribute('data-review', 'done')
      await expect(card.getByTestId('changed-in-review')).toContainText('Verdadeiro')
    }
    await win.getByTestId('filter-changed').click()
    await expect(cards).toHaveCount(2)
  } finally {
    await app.close()
  }
})
