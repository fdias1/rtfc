// Log do processo main em `<dados>/logs/app.log` (JSON por linha), com rotação (M7).
// O backend grava o próprio `backend.log` na mesma pasta.

import { appendFileSync, existsSync, mkdirSync, renameSync, rmSync, statSync } from 'node:fs'
import { join } from 'node:path'
import { format } from 'node:util'

const MAX_BYTES = 5 * 1024 * 1024
const BACKUPS = 3
const TOKEN = /token=[^&\s'"]+/g

let file: string | null = null
let written = 0

function rotate(path: string): void {
  rmSync(`${path}.${BACKUPS}`, { force: true })
  for (let i = BACKUPS - 1; i >= 1; i--) {
    if (existsSync(`${path}.${i}`)) renameSync(`${path}.${i}`, `${path}.${i + 1}`)
  }
  if (existsSync(path)) renameSync(path, `${path}.1`)
  written = 0
}

function write(level: string, args: unknown[]): void {
  if (!file) return
  const line =
    JSON.stringify({
      ts: new Date().toISOString(),
      level,
      logger: 'main',
      msg: format(...args).replace(TOKEN, 'token=***')
    }) + '\n'
  try {
    if (written + line.length > MAX_BYTES) rotate(file)
    appendFileSync(file, line)
    written += line.length
  } catch {
    // disco cheio ou pasta apagada: o log no console continua
  }
}

/** Passa a gravar o console do main em arquivo. Devolve o caminho do log. */
export function setupFileLog(logsDir: string): string {
  mkdirSync(logsDir, { recursive: true })
  file = join(logsDir, 'app.log')
  written = existsSync(file) ? statSync(file).size : 0
  for (const level of ['log', 'info', 'warn', 'error'] as const) {
    const original = console[level].bind(console)
    console[level] = (...args: unknown[]) => {
      original(...args)
      write(level === 'log' ? 'info' : level, args)
    }
  }
  return file
}
