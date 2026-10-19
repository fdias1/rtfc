import { useEffect, useId, useState } from 'react'
import { CircleCheck, KeyRound, LoaderCircle, TriangleAlert } from 'lucide-react'
import type { LlmRoleData, LlmTestResult, ProviderData, SettingsData } from '@rtfc/protocol'
import { useSettings, type Role } from '../store/settings'
import { buttonClass } from './Dialog'

const ROLE_INFO: Record<Role, { title: string; hint: string }> = {
  extractor: {
    title: 'Extração de afirmações',
    hint: 'Roda a cada frase, então precisa ser rápido. Um modelo local (Ollama) não envia o texto para fora, mas ao vivo divide o computador com a transcrição e pode atrasar as duas.'
  },
  checker: {
    title: 'Checagem (veredicto)',
    hint: 'Analisa as fontes encontradas e decide o veredicto. Usado a partir da checagem de fatos.'
  }
}

const inputClass = 'w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text'

function RoleEditor({
  role,
  value,
  providers,
  onChange
}: {
  role: Role
  value: LlmRoleData
  providers: ProviderData[]
  onChange(v: LlmRoleData): void
}): React.JSX.Element {
  const listId = useId()
  const loadModels = useSettings((s) => s.models)
  const test = useSettings((s) => s.test)
  const [models, setModels] = useState<string[]>([])
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<LlmTestResult | null>(null)
  const provider = providers.find((p) => p.id === value.provider)
  const showBaseUrl = value.provider === 'openai_compatible' || value.provider === 'ollama'

  useEffect(() => {
    let alive = true
    void loadModels(value.provider, value.base_url ?? null).then((m) => alive && setModels(m))
    return () => {
      alive = false
    }
  }, [value.provider, value.base_url, loadModels, provider?.has_key])

  const runTest = async (): Promise<void> => {
    setTesting(true)
    setResult(null)
    setResult(await test(role, value))
    setTesting(false)
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3" data-testid={`role-${role}`}>
      <div>
        <p className="text-sm font-medium text-text">{ROLE_INFO[role].title}</p>
        <p className="text-xs text-text-muted">{ROLE_INFO[role].hint}</p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Provedor
          <select
            className={inputClass}
            value={value.provider}
            data-testid={`provider-${role}`}
            onChange={(e) => {
              const next = providers.find((p) => p.id === e.target.value)
              setResult(null)
              onChange({ provider: e.target.value, model: next?.suggested_models[0] ?? '', base_url: null })
            }}
          >
            {providers.map((p) => (
              <option key={p.id} value={p.id}>
                {p.label}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Modelo
          <input
            className={inputClass}
            value={value.model}
            list={listId}
            data-testid={`model-${role}`}
            onChange={(e) => {
              setResult(null)
              onChange({ ...value, model: e.target.value })
            }}
            placeholder={provider?.suggested_models[0]}
          />
          <datalist id={listId}>
            {(models.length ? models : (provider?.suggested_models ?? [])).map((m) => (
              <option key={m} value={m} />
            ))}
          </datalist>
        </label>
      </div>
      {showBaseUrl && (
        <label className="flex flex-col gap-1 text-xs text-text-muted">
          Endereço da API
          <input
            className={`${inputClass} font-mono text-xs`}
            value={value.base_url ?? ''}
            placeholder={provider?.default_base_url ?? 'https://…/v1'}
            onChange={(e) => onChange({ ...value, base_url: e.target.value || null })}
          />
        </label>
      )}
      <div className="flex items-center gap-3">
        <button type="button" className={buttonClass.secondary} onClick={() => void runTest()} disabled={testing}>
          {testing ? 'Testando…' : 'Testar conexão'}
        </button>
        {provider?.needs_key && !provider.has_key && (
          <span className="flex items-center gap-1 text-xs text-verdict-context">
            <KeyRound size={12} /> Falta a chave de API (abaixo)
          </span>
        )}
        {testing && <LoaderCircle size={14} className="animate-spin text-text-muted" />}
        {result && (
          <span
            className={`flex min-w-0 items-center gap-1 text-xs ${result.ok ? 'text-verdict-true' : 'text-verdict-false'}`}
            data-testid={`test-result-${role}`}
          >
            {result.ok ? <CircleCheck size={13} /> : <TriangleAlert size={13} className="shrink-0" />}
            <span className="truncate" title={result.message ?? undefined}>
              {result.ok ? `OK · ${((result.latency_ms ?? 0) / 1000).toFixed(1)} s` : result.message}
            </span>
          </span>
        )}
      </div>
    </div>
  )
}

function KeyRow({ provider }: { provider: ProviderData }): React.JSX.Element {
  const setKey = useSettings((s) => s.setKey)
  const [value, setValue] = useState('')
  const [busy, setBusy] = useState(false)

  const save = async (v: string | null): Promise<void> => {
    setBusy(true)
    await setKey(provider.id, v)
    setValue('')
    setBusy(false)
  }

  return (
    <div className="grid grid-cols-[9rem_1fr_auto] items-center gap-2" data-testid={`key-${provider.id}`}>
      <span className="flex flex-col text-sm text-text">
        {provider.label}
        <span className={`text-[11px] ${provider.has_key ? 'text-verdict-true' : 'text-text-muted'}`}>
          {provider.has_key ? 'chave configurada' : 'sem chave'}
        </span>
      </span>
      <input
        type="password"
        autoComplete="off"
        spellCheck={false}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={provider.has_key ? 'Substituir chave…' : 'Cole a chave de API'}
        aria-label={`Chave de API do ${provider.label}`}
        className={`${inputClass} font-mono text-xs`}
      />
      <span className="flex gap-1">
        <button
          type="button"
          className={buttonClass.secondary}
          disabled={busy || !value.trim()}
          onClick={() => void save(value)}
        >
          Salvar
        </button>
        {provider.has_key && (
          <button type="button" className={buttonClass.secondary} disabled={busy} onClick={() => void save(null)}>
            Remover
          </button>
        )}
      </span>
    </div>
  )
}

/** Seção "Modelos de IA" das configurações. O rascunho só é salvo em `onSave`. */
export function LlmSettings({
  draft,
  onChange
}: {
  draft: SettingsData
  onChange(settings: SettingsData): void
}): React.JSX.Element {
  const all = useSettings((s) => s.providers)
  const providers = all.filter((p) => p.kind === 'llm')
  const keyed = all.filter((p) => p.needs_key)

  return (
    <div className="flex flex-col gap-3">
      <label className="flex items-center gap-2 text-sm text-text">
        <input
          type="checkbox"
          checked={draft.auto_extract}
          onChange={(e) => onChange({ ...draft, auto_extract: e.target.checked })}
          className="accent-primary"
        />
        Detectar afirmações automaticamente durante as sessões
      </label>
      <label className="flex items-center gap-2 text-sm text-text">
        <input
          type="checkbox"
          checked={draft.auto_check}
          onChange={(e) => onChange({ ...draft, auto_check: e.target.checked })}
          className="accent-primary"
        />
        Checar automaticamente cada afirmação detectada
      </label>
      <RoleEditor
        role="extractor"
        value={draft.extractor}
        providers={providers}
        onChange={(v) => onChange({ ...draft, extractor: v })}
      />
      <RoleEditor
        role="checker"
        value={draft.checker}
        providers={providers}
        onChange={(v) => onChange({ ...draft, checker: v })}
      />
      <div className="flex flex-col gap-2 rounded-md border border-border p-3">
        <p className="text-sm font-medium text-text">Chaves de API</p>
        <p className="text-xs text-text-muted">
          Guardadas no cofre do sistema (Keychain no macOS). O rtfc nunca as mostra de novo nem as grava em arquivos.
        </p>
        {keyed.map((p) => (
          <KeyRow key={p.id} provider={p} />
        ))}
      </div>
    </div>
  )
}
