# ADR 0005 — Busca sem conta e pipeline de checagem

**Status:** aceito · 2026-10-19 · Marco M6 (substitui a escolha da Tavily do PRD v1.0)

## Busca
- **Padrão: SearXNG local** (Docker, `infra/searxng/settings.yml`, API JSON em `127.0.0.1:8888`). É software livre, não exige conta nem tem limite de plano, e agrega Google, Brave, DuckDuckGo, Wikipedia… As buscas saem da máquina do usuário.
- **Reserva automática: DuckDuckGo** (`ddgs`, sem chave) quando o provedor principal falha. Não é oficial e sofre bloqueio com muitas buscas seguidas; serve de reserva, não de base.
- **Tavily: opcional**, com chave no keyring (`rtfc`/`tavily`).
- Sem a Tavily, o texto das páginas é extraído pelo próprio rtfc (`httpx` + `trafilatura`, 8 s de timeout, 3 MB no máximo). Quando a página não pode ser lida, o snippet do buscador vale como evidência fraca.
- Licenças: o SearXNG é AGPL, mas roda como **serviço separado**, acessado por HTTP e sem código incorporado, o que não conflita com a PolyForm NC. ddgs (MIT), trafilatura (Apache-2.0).

## Pipeline (por afirmação)
1. **Consultas:** 2–4, geradas pelo LLM de checagem no idioma do discurso.
2. **Busca** em paralelo.
3. **Ranking:** checadores > oficiais > imprensa > outros, depois quantas consultas acharam a página; no máximo 2 por domínio; redes sociais e domínios bloqueados são removidos.
4. **Leitura:** top 10, até 6 evidências com o trecho mais relevante (~1.600 caracteres).
5. **Veredicto** em JSON validado.
6. **Integridade, aplicada por código:**
   - o modelo cita **números de evidência**, nunca URLs, então não tem como inventar fonte;
   - números inexistentes ou repetidos são descartados;
   - citações que não aparecem na evidência são apagadas;
   - com menos de 2 fontes válidas, o veredicto vira **inconclusivo**, com confiança ≤ 0,3.

## Fila
- **Workers:** 3 por padrão, configurável.
- **Prioridade:** pedido manual > automático.
- **Cancelar:** cancelar a task aborta a busca e o LLM em andamento.
- **Rechecar e repetidas:** rechecar recoloca a afirmação na fila; as repetidas acompanham a original.
- **Descarte:** sempre prevalece sobre um resultado que chega depois.
- **Ao reabrir o app:** checagens que estavam pendentes ficam como "canceladas".
- Os eventos vão para todas as conexões, porque uma checagem pode terminar depois do fim da sessão.

## Medições (M2 Pro, 16 GB, sessão ao vivo de 95 s; OpenAI gpt-5.4-mini + SearXNG)
| Métrica | Meta (PRD) | p90 |
|---|---|---|
| Transcrição | ≤ 3 s | 2,7 s |
| Extração | ≤ 5 s | 1,7 s |
| Checagem (afirmação → veredicto) | ≤ 30 s | 10,6 s |
| **Fala → veredicto** | ≤ 35 s | **17,8 s** |

11 afirmações: 2 verdadeiras, 1 falsa, 7 fora de contexto, 1 inconclusiva. A qualidade dos veredictos é avaliada no M8.
