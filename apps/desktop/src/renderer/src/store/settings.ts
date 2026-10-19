// Configurações de LLM no backend (as chaves nunca voltam para a UI: só se existem).

import { create } from 'zustand'
import type {
  LlmRoleData,
  LlmTestResult,
  ProviderData,
  SearchSettingsData,
  SearchTestResult,
  SettingsData
} from '@rtfc/protocol'
import { backend } from '../lib/connection'

export type Role = 'extractor' | 'checker'

interface SettingsState {
  settings: SettingsData | null
  providers: ProviderData[]
  error: string | null
  load(): Promise<void>
  save(settings: SettingsData): Promise<boolean>
  setKey(provider: string, value: string | null): Promise<void>
  test(role: Role, config: LlmRoleData): Promise<LlmTestResult | null>
  models(provider: string, baseUrl: string | null): Promise<string[]>
  testSearch(search: SearchSettingsData): Promise<SearchTestResult | null>
}

function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

export const useSettings = create<SettingsState>((set) => ({
  settings: null,
  providers: [],
  error: null,

  async load() {
    try {
      const reply = await backend.request({ type: 'settings.get' })
      if (reply.type === 'settings.result') set({ settings: reply.settings, providers: reply.providers, error: null })
    } catch (err) {
      set({ error: errorMessage(err) })
    }
  },

  async save(settings) {
    const reply = await backend.request({ type: 'settings.set', settings })
    if (reply.type === 'settings.result') {
      set({ settings: reply.settings, providers: reply.providers, error: null })
      return true
    }
    set({ error: reply.type === 'error' ? reply.message : 'resposta inesperada' })
    return false
  },

  async setKey(provider, value) {
    const reply = await backend.request({ type: 'secret.set', provider, value })
    if (reply.type === 'settings.result') set({ providers: reply.providers, error: null })
    else if (reply.type === 'error') set({ error: reply.message })
  },

  async test(role, config) {
    try {
      const reply = await backend.request({ type: 'llm.test', role, config })
      return reply.type === 'llm.test.result' ? reply : null
    } catch (err) {
      return {
        type: 'llm.test.result',
        id: '',
        ok: false,
        model: config.model,
        latency_ms: null,
        message: errorMessage(err)
      }
    }
  },

  async testSearch(search) {
    try {
      const reply = await backend.request({ type: 'search.test', search })
      return reply.type === 'search.test.result' ? reply : null
    } catch (err) {
      return {
        type: 'search.test.result',
        id: '',
        ok: false,
        provider: search.provider,
        results: 0,
        latency_ms: null,
        message: errorMessage(err)
      }
    }
  },

  async models(provider, baseUrl) {
    try {
      const reply = await backend.request({ type: 'llm.models', provider, base_url: baseUrl })
      return reply.type === 'llm.models.result' ? reply.models : []
    } catch {
      return []
    }
  }
}))
