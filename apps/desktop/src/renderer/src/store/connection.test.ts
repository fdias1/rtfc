import { describe, expect, it } from 'vitest'
import { summarize } from './connection'

describe('summarize', () => {
  it('só está conectado com sidecar pronto e socket aberto', () => {
    expect(summarize({ state: 'ready', restarts: 0 }, 'open')).toBe('connected')
    expect(summarize({ state: 'ready', restarts: 0 }, 'connecting')).toBe('connecting')
    expect(summarize({ state: 'restarting', restarts: 1 }, 'closed')).toBe('connecting')
    expect(summarize({ state: 'failed', restarts: 5 }, 'closed')).toBe('failed')
  })
})
