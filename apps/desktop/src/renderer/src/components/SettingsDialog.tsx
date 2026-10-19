import { useEffect, useState, type ReactNode } from 'react'
import type { AppInfo } from '@shared/ipc'
import { useSession, type LanguageChoice } from '../store/session'
import { useTranscript } from '../store/transcript'
import { Dialog, buttonClass } from './Dialog'

function Section({ title, children }: { title: string; children: ReactNode }): React.JSX.Element {
  return (
    <section className="flex flex-col gap-2 border-b border-border py-4 first:pt-0 last:border-0 last:pb-0">
      <h3 className="text-xs font-semibold tracking-wide text-text-muted uppercase">{title}</h3>
      {children}
    </section>
  )
}

function Row({ label, children }: { label: string; children: ReactNode }): React.JSX.Element {
  return (
    <div className="grid grid-cols-[10rem_1fr] items-center gap-3 text-sm">
      <span className="text-text-muted">{label}</span>
      <div className="min-w-0">{children}</div>
    </div>
  )
}

/** Esqueleto das configurações (M3). Modelos de IA e busca entram no M5/M6. */
export function SettingsDialog({ onClose }: { onClose(): void }): React.JSX.Element {
  const language = useSession((s) => s.language)
  const setLanguage = useSession((s) => s.setLanguage)
  const stt = useTranscript((s) => s.stt)
  const [info, setInfo] = useState<AppInfo | null>(null)

  useEffect(() => {
    void window.rtfc.getAppInfo().then(setInfo)
  }, [])

  return (
    <Dialog
      title="Configurações"
      onClose={onClose}
      width="max-w-2xl"
      footer={
        <button type="button" className={buttonClass.primary} onClick={onClose}>
          Fechar
        </button>
      }
    >
      <div data-testid="settings">
        <Section title="Geral">
          <Row label="Idioma padrão">
            <select
              value={language}
              onChange={(e) => setLanguage(e.target.value as LanguageChoice)}
              className="rounded-md border border-border bg-surface px-2 py-1 text-sm"
            >
              <option value="pt">Português</option>
              <option value="en">Inglês</option>
              <option value="es">Espanhol</option>
              <option value="auto">Detectar automaticamente</option>
            </select>
          </Row>
          <Row label="Pasta das sessões">
            <code className="block truncate font-mono text-xs text-text-muted" title={info?.sessionsDir}>
              {info?.sessionsDir ?? '…'}
            </code>
          </Row>
        </Section>

        <Section title="Transcrição (local)">
          <Row label="Motor">{stt?.engine ?? '—'}</Row>
          <Row label="Modelo">{stt?.model ?? '—'}</Row>
          <p className="text-xs text-text-muted">
            Escolhido automaticamente para este computador. A troca de modelo pela interface chega numa próxima versão.
          </p>
        </Section>

        <Section title="Modelos de IA e busca">
          <p className="text-xs text-text-muted">
            Provedores de LLM (OpenAI, Gemini, Claude, Ollama…), chaves de API e busca chegam com a extração e a
            checagem de afirmações.
          </p>
        </Section>

        <Section title="Sobre">
          <Row label="Versão">{info?.version ?? '…'}</Row>
          <Row label="Licença">PolyForm Noncommercial 1.0.0</Row>
        </Section>
      </div>
    </Dialog>
  )
}
