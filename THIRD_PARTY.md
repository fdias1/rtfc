# Licenças de terceiros

O rtfc é distribuído sob PolyForm Noncommercial 1.0.0. Por isso, **só são aceitas dependências com licenças permissivas** (MIT, BSD, ISC, Apache-2.0, MPL-2.0, OFL para fontes) **ou LGPL com ligação dinâmica**. Dependências GPL/AGPL são bloqueadas no CI (`pnpm licenses:check`).

## Componentes principais

| Componente | Licença | Uso |
|---|---|---|
| Electron | MIT | Shell desktop |
| React, Zustand | MIT | UI |
| Tailwind CSS | MIT | Estilos |
| Inter, JetBrains Mono | OFL-1.1 | Fontes embutidas |
| Lucide | ISC | Ícones |
| FastAPI, Uvicorn, Pydantic | MIT / BSD-3-Clause | Backend |

## Transcrição

| Componente | Licença |
|---|---|
| faster-whisper, CTranslate2 | MIT |
| mlx, mlx-whisper (só macOS arm64) | MIT |
| onnxruntime | MIT |
| PyTorch (dependência do mlx-whisper) | BSD-3-Clause |

## Modelos (pesos)

Baixados sob demanda do Hugging Face Hub; não vêm no instalador.

| Modelo | Licença |
|---|---|
| Whisper (OpenAI), incl. conversões `Systran/faster-whisper-*`, `mobiuslabsgmbh/faster-whisper-large-v3-turbo` e `mlx-community/whisper-*` | MIT |
| Silero VAD (embutido no faster-whisper) | MIT |
| Qwen3 (Alibaba), via Ollama — LLM local padrão | Apache-2.0 |

## Busca e checagem

| Componente | Licença | Observação |
|---|---|---|
| LiteLLM | MIT | Camada de provedores de LLM |
| RapidFuzz | MIT | Deduplicação e validação de citações |
| ddgs | MIT | Busca DuckDuckGo (reserva) |
| trafilatura | Apache-2.0 | Texto principal das páginas |
| SearXNG | AGPL-3.0 | **Não incorporado**: roda como serviço separado (Docker) acessado por HTTP; o rtfc só traz o arquivo de configuração |

## Binários

- **ffmpeg**: deve ser empacotado em build **LGPL** (sem `--enable-gpl`), ligado dinamicamente ou executado como processo separado.
