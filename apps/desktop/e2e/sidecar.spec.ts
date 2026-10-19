/// <reference lib="dom" />
// Aceite do M0: o app abre, o backend sobe sozinho, e matar o Python reconecta automaticamente.

import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { _electron as electron, expect, test } from '@playwright/test'
import type { SidecarStatus } from '../src/shared/ipc'
import { TEST_ENV } from './helpers'
import type {} from '../src/preload/index.d'

test('backend sobe com o app e se recupera depois de morrer', async () => {
  const app = await electron.launch({
    args: [resolve(__dirname, '..')],
    env: { ...process.env, ...TEST_ENV, RTFC_SESSIONS_DIR: mkdtempSync(join(tmpdir(), 'rtfc-e2e-')) } as Record<
      string,
      string
    >
  })
  try {
    const win = await app.firstWindow()
    const status = win.getByTestId('connection-status')

    await expect(status).toHaveAttribute('data-state', 'connected', { timeout: 45_000 })
    await expect(status).toContainText('Backend conectado')

    const before = await win.evaluate(() => window.rtfc.getSidecarStatus())
    expect(before.pid).toBeGreaterThan(0)
    process.kill(before.pid!, 'SIGKILL')

    await expect(status).not.toHaveAttribute('data-state', 'connected', { timeout: 10_000 })
    await expect(status).toHaveAttribute('data-state', 'connected', { timeout: 45_000 })

    const after: SidecarStatus = await win.evaluate(() => window.rtfc.getSidecarStatus())
    expect(after.pid).not.toBe(before.pid)
    expect(after.restarts).toBe(1)
  } finally {
    await app.close()
  }
})
