import { defineConfig } from '@playwright/test'

/** Teste de resistência (M7): fora da suíte normal, roda à mão por ~2 h. */
export default defineConfig({
  testDir: './soak',
  retries: 0,
  workers: 1,
  reporter: 'list'
})
