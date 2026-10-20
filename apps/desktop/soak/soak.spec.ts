// Teste de resistência do M7: sessão ao vivo longa (padrão 2 h) com o microfone falso em loop.
//
// Usa o STT e a diarização reais (os padrões da máquina) e o LLM/busca falsos, para medir o
// app e não a internet. A cada minuto grava memória do sidecar e do renderer, latência da
// transcrição, segmentos e checagens pendentes em soak/out/<data>.csv.
//
// pnpm --filter @rtfc/desktop soak            (RTFC_SOAK_MIN=10 para uma rodada curta)

import { execFileSync } from 'node:child_process'
import { appendFileSync, mkdirSync, writeFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { expect, test } from '@playwright/test'
import { launchApp } from '../e2e/helpers'

const MINUTES = Number(process.env.RTFC_SOAK_MIN ?? 120)
const AUDIO = process.env.RTFC_SOAK_WAV ?? resolve(__dirname, '../../../eval/diarization/out/debate.wav')

/** Memória (MB) do processo Python do backend. No macOS usa o `footprint`, que conta também a
 * memória de GPU do MLX (o RSS do `ps` não conta). */
function sidecarMb(): number {
  const out = execFileSync('ps', ['-axww', '-o', 'pid=,rss=,command='], { encoding: 'utf8' })
  const rows = out
    .split('\n')
    .filter((l) => /python\S* -m rtfc\b/.test(l))
    .map((l) => l.trim().split(/\s+/))
  let best = 0
  for (const [pid, rss] of rows) {
    let mb = Number(rss) / 1024
    if (process.platform === 'darwin') {
      try {
        const fp = execFileSync('footprint', ['-p', pid!], { encoding: 'utf8' })
        const m = /Footprint:\s+([\d.]+)\s+(MB|GB)/.exec(fp)
        if (m) mb = Number(m[1]) * (m[2] === 'GB' ? 1024 : 1)
      } catch {
        // sem permissão ou processo já saiu: fica o RSS
      }
    }
    best = Math.max(best, mb)
  }
  return best
}

test('sessão ao vivo longa sem travar nem vazar memória', async () => {
  test.setTimeout((MINUTES + 10) * 60_000)
  const { app, win } = await launchApp({
    RTFC_FAKE_MIC_WAV: AUDIO,
    RTFC_STT_ENGINE: '',
    RTFC_STT_MODEL: '',
    RTFC_DIARIZER: ''
  })
  const outDir = resolve(__dirname, 'out')
  mkdirSync(outDir, { recursive: true })
  const csv = join(outDir, `${new Date().toISOString().replace(/[:.]/g, '-')}.csv`)
  writeFileSync(csv, 'min,sidecar_mb,renderer_mb,main_mb,latency_s,segments,claims,pending\n')
  try {
    await expect(win.getByTestId('stt-status')).toHaveAttribute('data-state', 'ready', { timeout: 300_000 })
    await win.getByTestId('start-mic').click()
    await expect(win.getByTestId('transcript-segment').first()).toBeVisible({ timeout: 60_000 })
    const start = Date.now()
    for (let min = 1; min <= MINUTES; min++) {
      await win.waitForTimeout(start + min * 60_000 - Date.now())
      const metrics = await app.evaluate(({ app: a }) => a.getAppMetrics())
      const kb = (type: string): number =>
        metrics.filter((m) => m.type === type).reduce((acc, m) => acc + m.memory.workingSetSize, 0)
      const latencyText =
        (await win
          .getByTestId('latency')
          .textContent()
          .catch(() => '')) ?? ''
      const row = [
        min,
        sidecarMb().toFixed(0),
        (kb('Tab') / 1024).toFixed(0),
        (kb('Browser') / 1024).toFixed(0),
        latencyText.match(/[\d.]+/)?.[0] ?? '',
        await win.getByTestId('transcript-segment').count(),
        await win.getByTestId('claim-card').count(),
        await win
          .locator(
            '[data-testid="claim-status"][data-status="queued"], [data-testid="claim-status"][data-status="checking"]'
          )
          .count()
      ]
      appendFileSync(csv, row.join(',') + '\n')
      console.log(`[soak] ${row.join(' ')}`)
      await expect(win.getByTestId('active-session')).toBeVisible()
    }
    await win.getByTestId('stop-session').click()
    await expect(win.getByTestId('active-session')).toBeHidden({ timeout: 120_000 })
  } finally {
    await app.close()
  }
})
