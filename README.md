# rtfc — Real Time Fact Checker

App desktop que ouve discursos, conversas, vídeos e transmissões, transcreve localmente e checa as afirmações factuais contra fontes públicas, com veredicto (**Verdadeiro**, **Fora de contexto**, **Falso**, **Inconclusivo**) e links das fontes.

- Produto: [docs/PRD.md](docs/PRD.md)
- Plano de implementação: [docs/PLAN.md](docs/PLAN.md)

## Estrutura

```
apps/desktop      Electron + React + TypeScript (UI e captura de áudio)
backend           Python 3.12 + FastAPI (STT, diarização, LLM, busca, checagem)
packages/protocol Tipos TS gerados a partir dos modelos Pydantic do backend
```

## Desenvolvimento

Pré-requisitos: Node 22+, pnpm 10+, [uv](https://docs.astral.sh/uv/), ffmpeg.

```bash
pnpm install
pnpm backend:sync        # uv sync no backend Python
pnpm dev                  # abre o app; o backend Python sobe sozinho
```

Outros comandos:

```bash
pnpm lint            # ESLint + ruff
pnpm typecheck       # tsc + mypy
pnpm test            # vitest + pytest
pnpm --filter @rtfc/desktop test:e2e  # E2E do Electron (Playwright)
pnpm protocol:gen    # regenera os tipos TS do protocolo
pnpm licenses:check  # bloqueia dependências GPL/AGPL
```

## Licença

[PolyForm Noncommercial 1.0.0](LICENSE.md) — uso, estudo e modificação livres para fins não comerciais; qualquer uso comercial (inclusive cobrar pelo app) é proibido. Licenças de terceiros em [THIRD_PARTY.md](THIRD_PARTY.md).
