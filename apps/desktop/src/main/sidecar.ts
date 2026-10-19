// Ciclo de vida do backend Python: spawn, health check, reinício automático e encerramento.

import { spawn, type ChildProcess } from 'node:child_process'
import { randomBytes } from 'node:crypto'
import { EventEmitter } from 'node:events'
import { existsSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { app } from 'electron'
import type { SidecarStatus } from '@shared/ipc'
import { LineSplitter, backoffDelay, parseReadyLine } from './sidecar-utils'

/** Falhas seguidas (sair antes de ficar pronto, ou logo depois) até desistir. */
const MAX_CONSECUTIVE_FAILURES = 5
/** Um backend que ficou de pé por mais que isso conta como estável. */
const STABLE_AFTER_MS = 10_000
const READY_TIMEOUT_MS = 30_000
const STOP_GRACE_MS = 3_000

interface Command {
  cmd: string
  args: string[]
  cwd: string
}

function resolveCommand(): Command {
  if (app.isPackaged) {
    // Empacotamento do backend (PyInstaller) chega no M9.
    const bin = join(
      process.resourcesPath,
      'backend',
      process.platform === 'win32' ? 'rtfc-backend.exe' : 'rtfc-backend'
    )
    return { cmd: bin, args: [], cwd: join(process.resourcesPath, 'backend') }
  }
  const backendDir = process.env.RTFC_BACKEND_DIR ?? resolve(app.getAppPath(), '../../backend')
  if (!existsSync(join(backendDir, 'pyproject.toml'))) {
    throw new Error(`backend não encontrado em ${backendDir} (defina RTFC_BACKEND_DIR)`)
  }
  return {
    cmd: process.env.RTFC_UV ?? 'uv',
    args: ['run', '--project', backendDir, 'python', '-m', 'rtfc'],
    cwd: backendDir
  }
}

export interface SidecarOptions {
  /** Pasta onde o backend cria as sessões (`RTFC_SESSIONS_DIR`). */
  sessionsDir: string
}

export class SidecarManager extends EventEmitter<{ status: [SidecarStatus] }> {
  private child: ChildProcess | null = null
  private status: SidecarStatus = { state: 'stopped', restarts: 0 }
  private stopping = false
  private failures = 0
  private readyAt = 0
  private restartTimer: NodeJS.Timeout | null = null

  constructor(private readonly options: SidecarOptions) {
    super()
  }

  getStatus(): SidecarStatus {
    return this.status
  }

  start(): void {
    this.stopping = false
    this.failures = 0
    this.spawnChild()
  }

  /** Reinício pedido pelo usuário (por exemplo, depois de `failed`). */
  async restart(): Promise<void> {
    await this.stop()
    this.start()
  }

  async stop(): Promise<void> {
    this.stopping = true
    if (this.restartTimer) clearTimeout(this.restartTimer)
    const child = this.child
    if (!child || child.exitCode !== null || child.signalCode !== null) {
      this.setStatus({ state: 'stopped' })
      return
    }
    await new Promise<void>((done) => {
      const term = setTimeout(() => child.kill('SIGTERM'), STOP_GRACE_MS)
      const kill = setTimeout(() => child.kill('SIGKILL'), STOP_GRACE_MS * 2)
      child.once('exit', () => {
        clearTimeout(term)
        clearTimeout(kill)
        done()
      })
      // Fechar o stdin é o sinal de encerramento gracioso (o backend observa o EOF).
      child.stdin?.end()
    })
    this.setStatus({ state: 'stopped' })
  }

  private setStatus(patch: Partial<SidecarStatus>): void {
    const next: SidecarStatus = { ...this.status, ...patch }
    if (next.state !== 'ready') {
      delete next.port
      delete next.token
    }
    this.status = next
    this.emit('status', next)
  }

  private spawnChild(): void {
    let command: Command
    try {
      command = resolveCommand()
    } catch (err) {
      this.setStatus({ state: 'failed', lastError: String(err) })
      return
    }

    const token = randomBytes(32).toString('hex')
    this.setStatus({ state: this.status.restarts > 0 ? 'restarting' : 'starting', pid: undefined })

    const child = spawn(command.cmd, command.args, {
      cwd: command.cwd,
      env: {
        ...process.env,
        RTFC_TOKEN: token,
        RTFC_SESSIONS_DIR: this.options.sessionsDir,
        PYTHONUNBUFFERED: '1',
        PYTHONUTF8: '1'
      },
      stdio: ['pipe', 'pipe', 'pipe']
    })
    this.child = child
    let ready = false
    let lastStderr = ''

    const readyTimeout = setTimeout(() => {
      if (!ready) {
        lastStderr ||= 'backend não respondeu a tempo'
        child.kill('SIGKILL')
      }
    }, READY_TIMEOUT_MS)

    const out = new LineSplitter()
    child.stdout?.setEncoding('utf8').on('data', (chunk: string) => {
      for (const line of out.push(chunk)) {
        const readyLine = !ready ? parseReadyLine(line) : null
        if (readyLine) {
          ready = true
          clearTimeout(readyTimeout)
          void this.onReady(child, readyLine.port, token, readyLine.pid ?? child.pid)
        } else if (line) {
          console.log(`[backend] ${line}`)
        }
      }
    })

    const err = new LineSplitter()
    child.stderr?.setEncoding('utf8').on('data', (chunk: string) => {
      for (const line of err.push(chunk)) {
        if (!line) continue
        lastStderr = line
        console.error(`[backend] ${line}`)
      }
    })

    child.on('error', (e) => {
      lastStderr = e.message
    })

    child.on('exit', (code, signal) => {
      clearTimeout(readyTimeout)
      if (this.child === child) this.child = null
      if (this.stopping) return
      this.scheduleRestart(`backend saiu (code=${code}, signal=${signal}) ${lastStderr}`.trim())
    })
  }

  private async onReady(child: ChildProcess, port: number, token: string, pid: number | undefined): Promise<void> {
    for (let i = 0; i < 20; i++) {
      if (this.child !== child) return
      try {
        const res = await fetch(`http://127.0.0.1:${port}/health`, {
          headers: { Authorization: `Bearer ${token}` }
        })
        if (res.ok) {
          this.readyAt = Date.now()
          this.setStatus({ state: 'ready', port, token, pid, lastError: undefined })
          return
        }
      } catch {
        // ainda subindo
      }
      await new Promise((r) => setTimeout(r, 150))
    }
    child.kill('SIGKILL')
  }

  private scheduleRestart(reason: string): void {
    const wasStable = this.readyAt > 0 && Date.now() - this.readyAt > STABLE_AFTER_MS
    this.failures = wasStable ? 1 : this.failures + 1
    this.readyAt = 0

    if (this.failures >= MAX_CONSECUTIVE_FAILURES) {
      this.setStatus({ state: 'failed', lastError: reason })
      return
    }
    const delay = backoffDelay(this.failures - 1)
    this.setStatus({ state: 'restarting', restarts: this.status.restarts + 1, lastError: reason })
    this.restartTimer = setTimeout(() => this.spawnChild(), delay)
  }
}
