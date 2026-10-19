// Converte uma seleção do DOM na transcrição em segmento/palavra e tempos.
// Cada palavra é um <span data-seg="i" data-word="j">; o resto (timestamps, parcial) é ignorado.

import type { TranscriptSegmentData } from '@rtfc/protocol'
import type { TranscriptSelection } from '../store/transcript'

interface WordRef {
  segment: number
  word: number
}

function wordRef(node: Node | null): WordRef | null {
  const el = node instanceof Element ? node : node?.parentElement
  const span = el?.closest<HTMLElement>('[data-word]')
  if (!span) return null
  return { segment: Number(span.dataset.seg), word: Number(span.dataset.word) }
}

function compare(a: WordRef, b: WordRef): number {
  return a.segment - b.segment || a.word - b.word
}

/** Primeira/última palavra dentro do range (cobre seleções que começam ou terminam fora de uma palavra). */
function boundaryWords(range: Range, root: HTMLElement): [WordRef, WordRef] | null {
  const spans = Array.from(root.querySelectorAll<HTMLElement>('[data-word]')).filter((el) => range.intersectsNode(el))
  const first = spans[0]
  const last = spans[spans.length - 1]
  if (!first || !last) return null
  return [wordRef(first)!, wordRef(last)!]
}

export function selectionFromDom(
  selection: Selection | null,
  root: HTMLElement,
  segments: TranscriptSegmentData[]
): TranscriptSelection | null {
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) return null
  const range = selection.getRangeAt(0)
  if (!root.contains(range.commonAncestorContainer)) return null

  const a = wordRef(selection.anchorNode)
  const b = wordRef(selection.focusNode)
  const bounds: [WordRef, WordRef] | null = a && b ? (compare(a, b) <= 0 ? [a, b] : [b, a]) : boundaryWords(range, root)
  if (!bounds) return null
  const [from, to] = bounds

  const words: string[] = []
  for (let s = from.segment; s <= to.segment; s++) {
    const seg = segments.find((x) => x.index === s)
    if (!seg) continue
    const start = s === from.segment ? from.word : 0
    const end = s === to.segment ? to.word : seg.words.length - 1
    for (let w = start; w <= end; w++) {
      const word = seg.words[w]
      if (word) words.push(word.text)
    }
  }
  const startWord = segments.find((x) => x.index === from.segment)?.words[from.word]
  const endWord = segments.find((x) => x.index === to.segment)?.words[to.word]
  if (!startWord || !endWord || words.length === 0) return null

  return { text: words.join(' '), startMs: startWord.start_ms, endMs: endWord.end_ms, from, to }
}
