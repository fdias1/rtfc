import { CircleAlert, CircleCheck, CircleHelp, CircleX } from 'lucide-react'
import type { CheckData, ClaimData } from '@rtfc/protocol'

export type Verdict = CheckData['verdict']

/** Cor, ícone e rótulo de cada veredicto. A cor nunca aparece sozinha (acessibilidade, PRD §8).
 * As classes são literais de propósito: o Tailwind só gera o que encontra escrito no código. */
export const VERDICT: Record<
  Verdict,
  {
    label: string
    icon: typeof CircleCheck
    text: string
    bg: string
    bar: string
    border: string
    decoration: string
  }
> = {
  verdadeiro: {
    label: 'Verdadeiro',
    icon: CircleCheck,
    text: 'text-verdict-true',
    bg: 'bg-verdict-true/10',
    bar: 'bg-verdict-true',
    border: 'border-l-verdict-true',
    decoration: 'decoration-verdict-true'
  },
  fora_de_contexto: {
    label: 'Fora de contexto',
    icon: CircleAlert,
    text: 'text-verdict-context',
    bg: 'bg-verdict-context/10',
    bar: 'bg-verdict-context',
    border: 'border-l-verdict-context',
    decoration: 'decoration-verdict-context'
  },
  falso: {
    label: 'Falso',
    icon: CircleX,
    text: 'text-verdict-false',
    bg: 'bg-verdict-false/10',
    bar: 'bg-verdict-false',
    border: 'border-l-verdict-false',
    decoration: 'decoration-verdict-false'
  },
  inconclusivo: {
    label: 'Inconclusivo',
    icon: CircleHelp,
    text: 'text-verdict-inconclusive',
    bg: 'bg-verdict-inconclusive/10',
    bar: 'bg-verdict-inconclusive',
    border: 'border-l-verdict-inconclusive',
    decoration: 'decoration-verdict-inconclusive'
  }
}

export const STAGE_LABEL: Record<NonNullable<ClaimData['stage']>, string> = {
  queries: 'Preparando a busca…',
  search: 'Buscando fontes…',
  reading: 'Lendo as páginas…',
  analysis: 'Analisando as evidências…'
}

export const TIER_LABEL: Record<string, string> = {
  primary: 'fonte primária',
  factchecker: 'checagem',
  official: 'oficial',
  press: 'imprensa',
  other: 'outra'
}

export const STANCE_LABEL: Record<string, string> = {
  apoia: 'apoia',
  refuta: 'refuta',
  contextualiza: 'contextualiza'
}

export function confidenceLabel(c: number): string {
  if (c >= 0.75) return 'alta'
  if (c >= 0.45) return 'média'
  return 'baixa'
}

/** Afirmação ainda sem resultado definitivo (na fila ou verificando). */
export function isPending(c: ClaimData): boolean {
  return c.status === 'queued' || c.status === 'checking'
}
