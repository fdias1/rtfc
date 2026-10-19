import { useState } from 'react'
import { CircleCheck, LoaderCircle, TriangleAlert } from 'lucide-react'
import type { SearchSettingsData, SearchTestResult } from '@rtfc/protocol'
import { useSettings } from '../store/settings'
import { buttonClass } from './Dialog'

const PROVIDERS: { value: SearchSettingsData['provider']; label: string; hint: string }[] = [
  {
    value: 'searxng',
    label: 'SearXNG (local)',
    hint: 'Software livre rodando no seu computador (Docker). Sem conta e sem limite de plano.'
  },
  {
    value: 'duckduckgo',
    label: 'DuckDuckGo',
    hint: 'Sem conta, mas não oficial: pode bloquear quando há muitas buscas seguidas.'
  },
  { value: 'tavily', label: 'Tavily', hint: 'Serviço pago com plano gratuito; precisa de chave (abaixo).' }
]

const inputClass = 'w-full rounded-md border border-border bg-surface px-2 py-1 text-sm text-text'

export function SearchSettings({
  value,
  onChange
}: {
  value: SearchSettingsData
  onChange(v: SearchSettingsData): void
}): React.JSX.Element {
  const testSearch = useSettings((s) => s.testSearch)
  const [testing, setTesting] = useState(false)
  const [result, setResult] = useState<SearchTestResult | null>(null)
  const current = PROVIDERS.find((p) => p.value === value.provider)

  const run = async (): Promise<void> => {
    setTesting(true)
    setResult(null)
    setResult(await testSearch(value))
    setTesting(false)
  }

  return (
    <div className="flex flex-col gap-2" data-testid="search-settings">
      <label className="flex flex-col gap-1 text-xs text-text-muted">
        Provedor de busca
        <select
          className={inputClass}
          value={value.provider}
          data-testid="search-provider"
          onChange={(e) => {
            setResult(null)
            onChange({ ...value, provider: e.target.value as SearchSettingsData['provider'] })
          }}
        >
          {PROVIDERS.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
        <span>{current?.hint}</span>
      </label>
      {value.provider === 'searxng' && (
        <>
          <label className="flex flex-col gap-1 text-xs text-text-muted">
            Endereço do SearXNG
            <input
              className={`${inputClass} font-mono text-xs`}
              value={value.searxng_url}
              onChange={(e) => onChange({ ...value, searxng_url: e.target.value })}
            />
          </label>
          <details className="text-xs text-text-muted">
            <summary className="cursor-pointer text-primary">Como subir o SearXNG local</summary>
            <p className="mt-1">Com o Docker instalado, rode uma vez na pasta do rtfc:</p>
            <code className="mt-1 block rounded bg-bg p-2 font-mono text-[11px] break-all text-text">
              docker run -d --name rtfc-searxng --restart unless-stopped -p 127.0.0.1:8888:8080 -e SEARXNG_SECRET=
              {'"$(openssl rand -hex 32)"'} -v &quot;$PWD/infra/searxng:/etc/searxng&quot; searxng/searxng
            </code>
          </details>
        </>
      )}
      {value.provider !== 'duckduckgo' && (
        <label className="flex items-center gap-2 text-sm text-text">
          <input
            type="checkbox"
            checked={value.fallback_duckduckgo}
            onChange={(e) => onChange({ ...value, fallback_duckduckgo: e.target.checked })}
            className="accent-primary"
          />
          Se a busca principal falhar, usar o DuckDuckGo como reserva
        </label>
      )}
      <label className="flex flex-col gap-1 text-xs text-text-muted">
        Domínios bloqueados (um por linha; redes sociais já são ignoradas)
        <textarea
          className={`${inputClass} h-16 font-mono text-xs`}
          value={value.blocked_domains.join('\n')}
          onChange={(e) => onChange({ ...value, blocked_domains: e.target.value.split('\n') })}
          placeholder="exemplo.com"
        />
      </label>
      <div className="flex items-center gap-3">
        <button type="button" className={buttonClass.secondary} onClick={() => void run()} disabled={testing}>
          {testing ? 'Buscando…' : 'Testar busca'}
        </button>
        {testing && <LoaderCircle size={14} className="animate-spin text-text-muted" />}
        {result && (
          <span
            className={`flex min-w-0 items-center gap-1 text-xs ${result.ok ? 'text-verdict-true' : 'text-verdict-false'}`}
            data-testid="search-test-result"
          >
            {result.ok ? <CircleCheck size={13} /> : <TriangleAlert size={13} className="shrink-0" />}
            <span className="truncate" title={result.message ?? undefined}>
              {result.ok
                ? `OK · ${result.results} resultados em ${((result.latency_ms ?? 0) / 1000).toFixed(1)} s`
                : result.message}
            </span>
          </span>
        )}
      </div>
    </div>
  )
}
