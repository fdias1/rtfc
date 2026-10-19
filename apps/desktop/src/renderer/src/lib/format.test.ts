import { describe, expect, it } from 'vitest'
import { basename, formatDuration, levelToFraction } from './format'

describe('formatDuration', () => {
  it('formata minutos e horas', () => {
    expect(formatDuration(0)).toBe('00:00')
    expect(formatDuration(75_000)).toBe('01:15')
    expect(formatDuration(3_725_000)).toBe('1:02:05')
    expect(formatDuration(-5)).toBe('00:00')
  })
})

describe('levelToFraction', () => {
  it('mapeia -60 dB..0 dB para 0..1', () => {
    expect(levelToFraction(0)).toBe(0)
    expect(levelToFraction(1)).toBe(1)
    expect(levelToFraction(0.001)).toBeCloseTo(0, 5) // -60 dB
    expect(levelToFraction(0.1)).toBeCloseTo(2 / 3, 5) // -20 dB
  })
})

describe('basename', () => {
  it('funciona com separadores de Unix e Windows', () => {
    expect(basename('/a/b/fala.mp3')).toBe('fala.mp3')
    expect(basename('C:\\videos\\debate.mp4')).toBe('debate.mp4')
  })
})
