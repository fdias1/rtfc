// Nomes dos falantes da sessão exibida (em andamento ou aberta do histórico).

import { useLibrary } from './library'
import { useSession } from './session'

const NONE: Record<string, string> = {}

export function useSpeakerNames(): Record<string, string> {
  const active = useSession((s) => s.active?.info.speakers)
  const viewing = useLibrary((s) => s.viewing?.speakers)
  return active ?? viewing ?? NONE
}
