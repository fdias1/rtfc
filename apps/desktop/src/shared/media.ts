// URLs do protocolo `rtfc-media://`, que serve arquivos locais (gravações e arquivos abertos)
// para os players do renderer. O main só serve caminhos explicitamente liberados.

export const MEDIA_SCHEME = 'rtfc-media'

export function mediaUrl(filePath: string): string {
  return `${MEDIA_SCHEME}://local/${encodeURIComponent(filePath)}`
}

export function pathFromMediaUrl(url: string): string | null {
  const prefix = `${MEDIA_SCHEME}://local/`
  if (!url.startsWith(prefix)) return null
  try {
    return decodeURIComponent(url.slice(prefix.length).split(/[?#]/, 1)[0] ?? '')
  } catch {
    return null
  }
}

export interface ByteRange {
  start: number
  end: number // inclusivo
}

/** Interpreta um header `Range: bytes=...` (só um intervalo). `null` = inválido/não satisfazível. */
export function parseRange(header: string, size: number): ByteRange | null {
  const m = /^bytes=(\d*)-(\d*)$/.exec(header.trim())
  if (!m || size <= 0) return null
  const [, a = '', b = ''] = m
  if (a === '' && b === '') return null
  let start: number
  let end: number
  if (a === '') {
    // sufixo: últimos N bytes
    const n = Number(b)
    if (n === 0) return null
    start = Math.max(0, size - n)
    end = size - 1
  } else {
    start = Number(a)
    end = b === '' ? size - 1 : Math.min(Number(b), size - 1)
  }
  if (start > end || start >= size) return null
  return { start, end }
}

const MIME: Record<string, string> = {
  ogg: 'audio/ogg',
  opus: 'audio/ogg',
  oga: 'audio/ogg',
  mp3: 'audio/mpeg',
  wav: 'audio/wav',
  m4a: 'audio/mp4',
  aac: 'audio/aac',
  flac: 'audio/flac',
  mp4: 'video/mp4',
  m4v: 'video/mp4',
  mov: 'video/quicktime',
  webm: 'video/webm',
  mkv: 'video/x-matroska'
}

export function mimeFor(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() ?? ''
  return MIME[ext] ?? 'application/octet-stream'
}

export const MEDIA_EXTENSIONS = Object.keys(MIME).concat(['avi', 'wma', 'aiff', 'ts', 'mpeg', 'mpg'])
