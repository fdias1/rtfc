// AudioWorklet: downmix para mono, conversão para Int16 e blocos de 100 ms para o backend.
// Roda na thread de áudio; não pode importar nada do app.

export {}

declare abstract class AudioWorkletProcessor {
  readonly port: MessagePort
  constructor(options?: { processorOptions?: unknown })
  abstract process(
    inputs: Float32Array[][],
    outputs: Float32Array[][],
    parameters: Record<string, Float32Array>
  ): boolean
}
declare function registerProcessor(
  name: string,
  ctor: new (options: { processorOptions?: unknown }) => AudioWorkletProcessor
): void
declare const sampleRate: number

export interface PcmChunkMessage {
  pcm: ArrayBuffer
  /** Pico e RMS do bloco, de 0 a 1 (para o VU meter). */
  peak: number
  rms: number
}

class PcmCaptureProcessor extends AudioWorkletProcessor {
  private readonly chunk: Int16Array
  private filled = 0
  private peak = 0
  private sumSquares = 0

  constructor(options: { processorOptions?: unknown }) {
    super(options)
    const chunkMs = (options.processorOptions as { chunkMs?: number } | undefined)?.chunkMs ?? 100
    this.chunk = new Int16Array(Math.round((sampleRate * chunkMs) / 1000))
  }

  process(inputs: Float32Array[][]): boolean {
    const channels = inputs[0]
    if (!channels || channels.length === 0) return true
    const frames = channels[0]!.length
    const n = channels.length

    for (let i = 0; i < frames; i++) {
      let v = 0
      for (let c = 0; c < n; c++) v += channels[c]![i]!
      v /= n
      if (v > 1) v = 1
      else if (v < -1) v = -1
      const abs = v < 0 ? -v : v
      if (abs > this.peak) this.peak = abs
      this.sumSquares += v * v
      this.chunk[this.filled++] = v < 0 ? v * 0x8000 : v * 0x7fff
      if (this.filled === this.chunk.length) this.flush()
    }
    return true
  }

  private flush(): void {
    const pcm = this.chunk.slice().buffer
    const msg: PcmChunkMessage = { pcm, peak: this.peak, rms: Math.sqrt(this.sumSquares / this.chunk.length) }
    this.port.postMessage(msg, [pcm])
    this.filled = 0
    this.peak = 0
    this.sumSquares = 0
  }
}

registerProcessor('pcm-capture', PcmCaptureProcessor)
