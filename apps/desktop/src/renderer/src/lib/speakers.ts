// Falantes (M4): nome para exibir e cor estável por rótulo ("S1", "S2"…).

const PALETTE = [
  'border-sky-300 bg-sky-50 text-sky-800',
  'border-amber-300 bg-amber-50 text-amber-800',
  'border-violet-300 bg-violet-50 text-violet-800',
  'border-emerald-300 bg-emerald-50 text-emerald-800',
  'border-rose-300 bg-rose-50 text-rose-800',
  'border-slate-300 bg-slate-50 text-slate-700'
]

/** Nome dado pelo usuário, ou "Falante N". */
export function speakerLabel(id: string | null | undefined, names: Record<string, string> = {}): string | null {
  if (!id) return null
  if (names[id]) return names[id]
  const n = /^S(\d+)$/.exec(id)
  return n ? `Falante ${n[1]}` : id
}

export function speakerColor(id: string): string {
  const n = /^S(\d+)$/.exec(id)
  const i = n ? Number(n[1]) - 1 : [...id].reduce((a, c) => a + c.charCodeAt(0), 0)
  return PALETTE[i % PALETTE.length]!
}

/** Rótulos na ordem em que aparecem. */
export function speakersInOrder(ids: (string | null | undefined)[]): string[] {
  return [...new Set(ids.filter((s): s is string => !!s))]
}
