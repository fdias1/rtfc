// Cliente WebSocket do backend: conexão, reconexão e requisições com `id`.

import { parseServerMessage, type ClientMessage, type ServerMessage } from '@rtfc/protocol'

export interface BackendClientEvents {
  onOpen(): void
  onClose(): void
  onMessage(msg: ServerMessage): void
}

type Pending = { resolve: (msg: ServerMessage) => void; reject: (err: Error) => void; timer: number }

const RECONNECT_MS = 1000
const REQUEST_TIMEOUT_MS = 5000

/** Distribui mensagens sem `id`, sem precisar do `Omit` sobre a união (que perderia o discriminador). */
type WithoutId<T> = T extends unknown ? Omit<T, 'id'> : never

export class BackendClient {
  private ws: WebSocket | null = null
  private url: string | null = null
  private pending = new Map<string, Pending>()
  private reconnectTimer: number | null = null
  private nextId = 1

  constructor(private readonly events: BackendClientEvents) {}

  /** (Re)conecta a um endereço. Se for o mesmo endereço já conectado, não faz nada. */
  connect(port: number, token: string): void {
    const url = `ws://127.0.0.1:${port}/ws?token=${token}`
    if (url === this.url && this.ws && this.ws.readyState <= WebSocket.OPEN) return
    this.disconnect()
    this.url = url
    this.open()
  }

  disconnect(): void {
    this.url = null
    if (this.reconnectTimer !== null) window.clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    const ws = this.ws
    this.ws = null
    ws?.close()
    this.failPending('desconectado')
  }

  request(msg: WithoutId<ClientMessage>): Promise<ServerMessage> {
    const ws = this.ws
    if (!ws || ws.readyState !== WebSocket.OPEN) return Promise.reject(new Error('sem conexão'))
    const id = String(this.nextId++)
    return new Promise((resolve, reject) => {
      const timer = window.setTimeout(() => {
        this.pending.delete(id)
        reject(new Error('timeout'))
      }, REQUEST_TIMEOUT_MS)
      this.pending.set(id, { resolve, reject, timer })
      ws.send(JSON.stringify({ ...msg, id }))
    })
  }

  private open(): void {
    const url = this.url
    if (!url) return
    const ws = new WebSocket(url)
    this.ws = ws
    ws.onopen = () => this.events.onOpen()
    ws.onmessage = (ev: MessageEvent<string>) => {
      const msg = parseServerMessage(ev.data)
      if (!msg) return
      const id = 'id' in msg ? msg.id : null
      const pending = id ? this.pending.get(id) : undefined
      if (id && pending) {
        window.clearTimeout(pending.timer)
        this.pending.delete(id)
        pending.resolve(msg)
      } else {
        this.events.onMessage(msg)
      }
    }
    ws.onclose = () => {
      if (this.ws !== ws) return
      this.ws = null
      this.failPending('conexão fechada')
      this.events.onClose()
      // Tenta de novo no mesmo endereço; se o backend reiniciou em outra porta,
      // o main avisa e `connect()` troca o endereço.
      if (this.url === url) this.reconnectTimer = window.setTimeout(() => this.open(), RECONNECT_MS)
    }
  }

  private failPending(reason: string): void {
    for (const p of this.pending.values()) {
      window.clearTimeout(p.timer)
      p.reject(new Error(reason))
    }
    this.pending.clear()
  }
}
