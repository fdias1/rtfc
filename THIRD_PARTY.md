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

## Modelos (pesos)

Serão listados aqui conforme forem integrados (Whisper — MIT; Silero VAD — MIT; pyannote — termos do Hugging Face; sherpa-onnx — Apache-2.0).

## Binários

- **ffmpeg**: deve ser empacotado em build **LGPL** (sem `--enable-gpl`), ligado dinamicamente ou executado como processo separado.
