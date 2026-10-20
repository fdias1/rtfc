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

Modelo de IA local (padrão, sem custo): instale o [Ollama](https://ollama.com) e baixe o modelo (~5 GB):

```bash
ollama pull qwen3:8b
```

Com mais de 16 GB de memória, o `qwen3:14b` (~9 GB) acerta mais e pode ser escolhido em **Configurações**.

Provedores online (OpenAI, Claude, Gemini…) podem ser escolhidos em **Configurações**; são mais rápidos, mas têm custo.

Busca (checagem de fatos): o padrão é um SearXNG local, sem conta. Com o Docker instalado, rode uma vez:

```bash
docker run -d --name rtfc-searxng --restart unless-stopped -p 127.0.0.1:8888:8080 -e SEARXNG_SECRET="$(openssl rand -hex 32)" -v "$PWD/infra/searxng:/etc/searxng" searxng/searxng
```

Sem ele, o rtfc usa o DuckDuckGo como reserva. Modelos de IA, chaves de API e busca ficam em **Configurações** no app (as chaves vão para o cofre do sistema).

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
