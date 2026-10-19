import { describe, expect, it } from 'vitest'
import { mediaUrl, mimeFor, parseRange, pathFromMediaUrl } from './media'

describe('mediaUrl / pathFromMediaUrl', () => {
  it('ida e volta com caminhos de Unix e Windows, espaços e acentos', () => {
    for (const p of ['/Users/fábio/Debate 2026.mp4', 'C:\\Users\\x\\fala#1.ogg']) {
      expect(pathFromMediaUrl(mediaUrl(p))).toBe(p)
    }
  })

  it('rejeita outros esquemas', () => {
    expect(pathFromMediaUrl('file:///etc/passwd')).toBeNull()
  })
})

describe('parseRange', () => {
  it('intervalos normais, abertos e sufixo', () => {
    expect(parseRange('bytes=0-99', 1000)).toEqual({ start: 0, end: 99 })
    expect(parseRange('bytes=500-', 1000)).toEqual({ start: 500, end: 999 })
    expect(parseRange('bytes=-100', 1000)).toEqual({ start: 900, end: 999 })
    expect(parseRange('bytes=900-5000', 1000)).toEqual({ start: 900, end: 999 })
  })

  it('inválidos', () => {
    expect(parseRange('bytes=1000-', 1000)).toBeNull()
    expect(parseRange('bytes=5-1', 1000)).toBeNull()
    expect(parseRange('bytes=-', 1000)).toBeNull()
    expect(parseRange('items=0-1', 1000)).toBeNull()
    expect(parseRange('bytes=0-1', 0)).toBeNull()
  })
})

describe('mimeFor', () => {
  it('conhece os formatos principais', () => {
    expect(mimeFor('/x/audio.ogg')).toBe('audio/ogg')
    expect(mimeFor('/x/VIDEO.MP4')).toBe('video/mp4')
    expect(mimeFor('/x/sem-extensao')).toBe('application/octet-stream')
  })
})
