// Captura ao vivo (microfone ou áudio do sistema) → blocos PCM s16le mono 48 kHz.

import workletUrl from './pcm-worklet.ts?worker&url'
import type { PcmChunkMessage } from './pcm-worklet'

export const CAPTURE_SAMPLE_RATE = 48_000

export type LiveSource = 'mic' | 'system'

export interface AudioLevel {
  peak: number
  rms: number
}

export interface CaptureOptions {
  deviceId?: string
  onChunk(pcm: ArrayBuffer): void
  onLevel(level: AudioLevel): void
  /** O SO ou o usuário encerrou o stream (dispositivo removido, compartilhamento parado…). */
  onEnded(): void
}

export interface LiveCapture {
  readonly sampleRate: number
  readonly label: string
  setPaused(paused: boolean): void
  stop(): Promise<void>
}

export class CaptureError extends Error {
  constructor(
    message: string,
    readonly code: 'permission' | 'no-audio' | 'unavailable'
  ) {
    super(message)
  }
}

async function openStream(source: LiveSource, deviceId?: string): Promise<MediaStream> {
  try {
    if (source === 'mic') {
      return await navigator.mediaDevices.getUserMedia({
        audio: {
          deviceId: deviceId ? { exact: deviceId } : undefined,
          channelCount: 1,
          // Sem processamento: queremos o áudio fiel para gravar e transcrever.
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false
        }
      })
    }
    // O main responde com a tela principal + áudio "loopback" (ver main/capture.ts).
    // Sem processamento: com cancelamento de eco ligado o Chromium remove justamente o som que
    // sai pelos alto-falantes, e a gravação do sistema fica muda.
    const stream = await navigator.mediaDevices.getDisplayMedia({
      video: true,
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }
    })
    for (const track of stream.getVideoTracks()) {
      track.stop()
      stream.removeTrack(track)
    }
    if (stream.getAudioTracks().length === 0) {
      throw new CaptureError('O sistema não forneceu o áudio da tela.', 'no-audio')
    }
    return stream
  } catch (err) {
    if (err instanceof CaptureError) throw err
    const name = err instanceof DOMException ? err.name : ''
    if (name === 'NotAllowedError' || name === 'SecurityError') {
      throw new CaptureError(
        source === 'mic' ? 'Sem permissão para usar o microfone.' : 'Sem permissão para capturar o áudio do sistema.',
        'permission'
      )
    }
    throw new CaptureError(`Não foi possível iniciar a captura: ${String(err)}`, 'unavailable')
  }
}

export async function startCapture(source: LiveSource, options: CaptureOptions): Promise<LiveCapture> {
  const stream = await openStream(source, options.deviceId)
  const track = stream.getAudioTracks()[0]!
  const ctx = new AudioContext({ sampleRate: CAPTURE_SAMPLE_RATE, latencyHint: 'interactive' })
  await ctx.audioWorklet.addModule(workletUrl)

  const input = ctx.createMediaStreamSource(stream)
  const node = new AudioWorkletNode(ctx, 'pcm-capture', {
    numberOfInputs: 1,
    numberOfOutputs: 1,
    channelCountMode: 'explicit',
    channelCount: 2,
    processorOptions: { chunkMs: 100 }
  })
  // Saída muda até o destination: garante que o grafo seja processado em todos os navegadores.
  const mute = ctx.createGain()
  mute.gain.value = 0
  input.connect(node).connect(mute).connect(ctx.destination)

  let paused = false
  let stopped = false
  node.port.onmessage = (ev: MessageEvent<PcmChunkMessage>) => {
    if (stopped) return
    if (paused) {
      options.onLevel({ peak: 0, rms: 0 })
      return
    }
    options.onLevel({ peak: ev.data.peak, rms: ev.data.rms })
    options.onChunk(ev.data.pcm)
  }

  const onEnded = (): void => {
    if (!stopped) options.onEnded()
  }
  track.addEventListener('ended', onEnded)

  return {
    sampleRate: ctx.sampleRate,
    label: track.label,
    setPaused: (p) => {
      paused = p
    },
    stop: async () => {
      if (stopped) return
      stopped = true
      track.removeEventListener('ended', onEnded)
      node.port.onmessage = null
      for (const t of stream.getTracks()) t.stop()
      input.disconnect()
      node.disconnect()
      await ctx.close()
    }
  }
}

export async function listMicrophones(): Promise<MediaDeviceInfo[]> {
  const devices = await navigator.mediaDevices.enumerateDevices()
  return devices.filter((d) => d.kind === 'audioinput')
}
