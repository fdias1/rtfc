# ADR 0001 — Formato da gravação e caminho do áudio

**Status:** aceito · 2026-10-19 · Marco M1

## Contexto
O PRD (RF7.2) exige gravação integral das sessões ao vivo, que sobreviva a um encerramento forçado, e o pipeline (VAD/Whisper) precisa de PCM mono 16 kHz.

## Decisão
- O renderer captura em **48 kHz mono** (AudioContext fixo em 48 kHz), converte para Int16 e envia blocos de 100 ms como frames binários no WebSocket.
- O backend abre **um único processo ffmpeg por sessão** que recebe esse PCM no stdin e produz duas saídas:
  1. `audio.ogg` — **Opus 48 kHz mono, 48 kbit/s** (~21 MB/h), páginas Ogg de 500 ms com `-flush_packets 1`;
  2. PCM **s16le 16 kHz mono** no stdout, que alimenta o ring buffer do pipeline.
- Arquivos de áudio/vídeo são decodificados pelo ffmpeg direto para 16 kHz; a "gravação" de uma sessão de arquivo é o próprio arquivo original.

## Consequências
- Qualidade boa para reouvir podcasts e música (16 kHz soaria abafado), com custo de banda irrelevante em localhost (96 KB/s).
- Reamostragem fica no ffmpeg (sem código de DSP próprio no JS).
- Spike no M2 Pro: após `SIGKILL` no ffmpeg com 10 s gravados, o `audio.ogg` reproduz 9 s — perda máxima ≈ 1 página + lookahead do encoder.
- Em dev usamos o ffmpeg do sistema (o do Homebrew é build GPL, aceitável por não ser distribuído). **No empacotamento (M9) o ffmpeg tem de ser build LGPL** com libopus (BSD).
