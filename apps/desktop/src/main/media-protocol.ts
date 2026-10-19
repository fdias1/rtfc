// Protocolo `rtfc-media://`: serve arquivos locais liberados para os players, com suporte a Range
// (necessário para o seek de <audio>/<video>).

import { createReadStream } from 'node:fs'
import { stat } from 'node:fs/promises'
import { resolve, sep } from 'node:path'
import { Readable } from 'node:stream'
import { protocol } from 'electron'
import { MEDIA_SCHEME, mimeFor, parseRange, pathFromMediaUrl } from '@shared/media'

const allowedFiles = new Set<string>()
const allowedDirs = new Set<string>()

export function allowMediaFile(filePath: string): void {
  allowedFiles.add(resolve(filePath))
}

export function allowMediaDir(dir: string): void {
  allowedDirs.add(resolve(dir) + sep)
}

function isAllowed(filePath: string): boolean {
  const abs = resolve(filePath)
  if (allowedFiles.has(abs)) return true
  for (const dir of allowedDirs) if (abs.startsWith(dir)) return true
  return false
}

/** Precisa rodar antes do `app.ready`. */
export function registerMediaScheme(): void {
  protocol.registerSchemesAsPrivileged([
    { scheme: MEDIA_SCHEME, privileges: { standard: true, secure: true, stream: true, supportFetchAPI: true } }
  ])
}

function body(filePath: string, start?: number, end?: number): ReadableStream {
  return Readable.toWeb(createReadStream(filePath, { start, end })) as ReadableStream
}

export function handleMediaProtocol(): void {
  protocol.handle(MEDIA_SCHEME, async (request) => {
    const filePath = pathFromMediaUrl(request.url)
    if (!filePath || !isAllowed(filePath)) return new Response('forbidden', { status: 403 })

    let size: number
    try {
      const info = await stat(filePath)
      if (!info.isFile()) return new Response('not found', { status: 404 })
      size = info.size
    } catch {
      return new Response('not found', { status: 404 })
    }

    const headers = { 'Content-Type': mimeFor(filePath), 'Accept-Ranges': 'bytes' }
    const rangeHeader = request.headers.get('range')
    if (!rangeHeader) {
      return new Response(body(filePath), { status: 200, headers: { ...headers, 'Content-Length': String(size) } })
    }
    const range = parseRange(rangeHeader, size)
    if (!range) {
      return new Response(null, { status: 416, headers: { ...headers, 'Content-Range': `bytes */${size}` } })
    }
    return new Response(body(filePath, range.start, range.end), {
      status: 206,
      headers: {
        ...headers,
        'Content-Length': String(range.end - range.start + 1),
        'Content-Range': `bytes ${range.start}-${range.end}/${size}`
      }
    })
  })
}
