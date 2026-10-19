// Funções puras do gerenciador do sidecar (testáveis sem Electron).

export interface ReadyLine {
  event: 'ready'
  port: number
  /** Pid do processo Python (pode diferir do filho direto, que em dev é o `uv`). */
  pid?: number
}

/** Reconhece a linha `{"event":"ready","port":N}` que o backend imprime ao subir. */
export function parseReadyLine(line: string): ReadyLine | null {
  const trimmed = line.trim()
  if (!trimmed.startsWith('{')) return null
  try {
    const data = JSON.parse(trimmed) as Partial<ReadyLine>
    if (data.event === 'ready' && Number.isInteger(data.port) && (data.port ?? 0) > 0) {
      const pid = Number.isInteger(data.pid) ? data.pid : undefined
      return { event: 'ready', port: data.port as number, pid }
    }
  } catch {
    // não é JSON: é log comum
  }
  return null
}

/** Espera antes da tentativa `attempt` (0, 1, 2…): 500 ms, 1 s, 2 s… até 10 s. */
export function backoffDelay(attempt: number): number {
  return Math.min(500 * 2 ** attempt, 10_000)
}

/** Separa um fluxo de chunks em linhas completas, guardando o resto incompleto. */
export class LineSplitter {
  private buffer = ''

  push(chunk: string): string[] {
    this.buffer += chunk
    const lines = this.buffer.split(/\r?\n/)
    this.buffer = lines.pop() ?? ''
    return lines
  }
}
