import type { SessionInfo } from '@rtfc/protocol'
import { basename } from './format'

const SOURCE: Record<SessionInfo['source'], string> = {
  mic: 'Microfone',
  system: 'Áudio do sistema',
  file: 'Arquivo'
}

export function sourceLabel(info: SessionInfo): string {
  return SOURCE[info.source]
}

/** Nome exibido: o título dado pelo usuário, o nome do arquivo ou a fonte. */
export function sessionTitle(info: SessionInfo): string {
  if (info.title) return info.title
  if (info.source === 'file' && info.file_path) return basename(info.file_path)
  return SOURCE[info.source]
}

export function sessionDate(info: SessionInfo): string {
  const d = new Date(info.started_at)
  return d.toLocaleString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit'
  })
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(0)} KB`
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`
}
