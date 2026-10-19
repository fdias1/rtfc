import { describe, expect, it } from 'vitest'
import { LineSplitter, backoffDelay, parseReadyLine } from './sidecar-utils'

describe('parseReadyLine', () => {
  it('reconhece a linha de pronto', () => {
    expect(parseReadyLine('{"event": "ready", "port": 51234, "pid": 99}')).toEqual({
      event: 'ready',
      port: 51234,
      pid: 99
    })
  })

  it('aceita linha sem pid', () => {
    expect(parseReadyLine('{"event":"ready","port":8000}')).toEqual({ event: 'ready', port: 8000, pid: undefined })
  })

  it('ignora logs e JSON inválido', () => {
    expect(parseReadyLine('INFO: Uvicorn running')).toBeNull()
    expect(parseReadyLine('{"event":"ready"}')).toBeNull()
    expect(parseReadyLine('{"event":"ready","port":0}')).toBeNull()
    expect(parseReadyLine('{oops')).toBeNull()
  })
})

describe('backoffDelay', () => {
  it('cresce exponencialmente até 10 s', () => {
    expect([0, 1, 2, 3, 10].map(backoffDelay)).toEqual([500, 1000, 2000, 4000, 10_000])
  })
})

describe('LineSplitter', () => {
  it('junta linhas quebradas entre chunks', () => {
    const s = new LineSplitter()
    expect(s.push('a\nb')).toEqual(['a'])
    expect(s.push('c\r\nd\n')).toEqual(['bc', 'd'])
    expect(s.push('')).toEqual([])
  })
})
