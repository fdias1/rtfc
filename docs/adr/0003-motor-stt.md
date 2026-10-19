# ADR 0003 — Motor e modelo de transcrição por plataforma

**Status:** aceito · 2026-10-19 · Marco M2

## Benchmark
`eval/stt/bench.py` no hardware de referência (**M2 Pro, 16 GB, macOS 26**), com 87 s de fala pt-BR sintetizada (voz Luciana; `eval/stt/make_reference.sh`), limpa e com ruído rosa.
- `win`: segundos para transcrever uma janela de 10 s (o custo de cada passo do streaming).
- `rtf`: modo arquivo (tempo ÷ duração).

| motor | modelo | win p50 | win p90 | rtf | WER limpo | WER ruído |
|---|---|---|---|---|---|---|
| faster-whisper (CPU int8) | small | 2,00 | 2,14 | 0,127 | 4,0% | 3,0% |
| faster-whisper (CPU int8) | medium | 5,11 | 5,93 | 0,458 | 0,5% | 0,5% |
| faster-whisper (CPU int8) | large-v3-turbo | 4,43 | 4,53 | 0,261 | 0,0% | 0,0% |
| mlx-whisper (Metal) | small | 0,41 | 0,41 | 0,033 | 4,0% | 3,0% |
| mlx-whisper (Metal) | medium | 1,07 | 1,11 | 0,074 | 0,5% | 0,5% |
| **mlx-whisper (Metal)** | **large-v3-turbo** | **1,27** | **1,35** | **0,068** | **0,0%** | **0,0%** |

Limitação: a fala sintetizada é mais limpa que um debate real. O WER absoluto é otimista, mas a comparação entre modelos vale. O M8 traz áudio real.

## Decisão
- **Apple Silicon:** `mlx-whisper` + `large-v3-turbo`. Melhor precisão e ~1,3 s por passo; 1 h de áudio em ~4 min.
- **Demais plataformas:** `faster-whisper` + `small` (int8 na CPU; float16 na CUDA, quando houver).
- Override por `RTFC_STT_ENGINE` / `RTFC_STT_MODEL` (a tela de configurações chega depois).
- O VAD é o Silero em ONNX que já vem com o faster-whisper, sem PyTorch.

## Consequências
- Na CPU, o passo do streaming (~2 s) passa do intervalo de 1 s. A transcrição continua correta, mas a latência ao vivo deve ficar acima da meta de 3 s em máquinas sem GPU. A validar no M9 em Windows/Linux; alternativas: modelo `base`, ou `small` na CUDA.
- O extra `mlx` (macOS arm64) traz PyTorch como dependência transitiva do `mlx-whisper` (~1 GB no venv). A rever no empacotamento (M9).
- Licenças: Whisper (MIT), faster-whisper/CTranslate2 (MIT), mlx/mlx-whisper (MIT), Silero VAD (MIT), onnxruntime (MIT).
