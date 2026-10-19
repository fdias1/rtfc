// Player da sessão exibida: posição atual (para destacar a palavra) e seek a partir da transcrição.

import { create } from 'zustand'

interface PlayerState {
  element: HTMLMediaElement | null
  currentMs: number
  playing: boolean
  attach(el: HTMLMediaElement | null): void
  seek(ms: number): void
}

let raf = 0

export const usePlayer = create<PlayerState>((set, get) => {
  // Enquanto toca, atualiza a posição a cada quadro: o `timeupdate` (~4 Hz) é lento demais
  // para destacar palavra por palavra.
  const tick = (): void => {
    const el = get().element
    if (!el) return
    set({ currentMs: el.currentTime * 1000 })
    if (!el.paused) raf = requestAnimationFrame(tick)
  }

  const onPlay = (): void => {
    set({ playing: true })
    cancelAnimationFrame(raf)
    raf = requestAnimationFrame(tick)
  }
  const onPause = (): void => {
    set({ playing: false })
    tick()
  }
  const onSeeked = (): void => tick()

  return {
    element: null,
    currentMs: 0,
    playing: false,

    attach(el) {
      const prev = get().element
      if (prev === el) return
      if (prev) {
        prev.removeEventListener('play', onPlay)
        prev.removeEventListener('pause', onPause)
        prev.removeEventListener('seeked', onSeeked)
      }
      cancelAnimationFrame(raf)
      if (el) {
        el.addEventListener('play', onPlay)
        el.addEventListener('pause', onPause)
        el.addEventListener('seeked', onSeeked)
      }
      set({ element: el, currentMs: 0, playing: false })
    },

    seek(ms) {
      const el = get().element
      if (!el) return
      el.currentTime = ms / 1000
      set({ currentMs: ms })
      void el.play().catch(() => undefined)
    }
  }
})
