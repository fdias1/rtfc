# ADR 0004 — Extração de afirmações

**Status:** aceito · 2026-10-19 · Marco M5

## Decisões
- **LiteLLM** como camada única de provedores (OpenAI, Anthropic, Gemini, DeepSeek, Mistral, Ollama, compatível com OpenAI). Saída estruturada por JSON Schema quando o modelo suporta; senão JSON + validação Pydantic com até 2 correções.
- **Chaves no keyring do SO** (serviço `rtfc`). A UI só sabe se a chave existe; nunca a recebe de volta.
- **Extrator por frase confirmada**: frases novas + ~60 s de contexto + afirmações já extraídas. No máximo 1 chamada em andamento por sessão; o que chega nesse meio-tempo é agrupado (até 8 frases).
- **Prompt com exemplos (few-shot)**: no Ollama, levou o recall de 78% → 89% e os falsos positivos de 22% → 0%.
- **Deduplicação léxica** (RapidFuzz `token_set_ratio ≥ 88`) em vez de embeddings, como previa o plano. Paráfrases quase idênticas são o caso comum ao vivo, e assim evitamos PyTorch/ONNX extra só para isso. O extrator também recebe a lista do que já foi extraído. Revisitar se o M8 mostrar duplicatas semânticas escapando.
- **Ancoragem aproximada** (`difflib` sobre janelas de palavras) do `source_text` devolvido pelo modelo; sem match, ancora na frase inteira.

## Medições (M2 Pro, 16 GB)
`eval/claims/run.py`, texto de referência, frase a frase:

| Extrator | Recall | Falsos positivos | Chamada p50 / p90 |
|---|---|---|---|
| OpenAI gpt-5.4-mini | 100% | 0% | 0,95 / 1,13 s |
| Ollama qwen3:8b (isolado) | 89% | 0% | 3,45 / 4,85 s |

Sessão **ao vivo** completa (Whisper large-v3-turbo + extrator, 90 s de fala):

| Extrator | Afirmações | Extração p50 / p90 | Transcrição p90 |
|---|---|---|---|
| OpenAI gpt-5.4-mini | 11 | 1,5 / **2,1 s** ✅ | 2,96 s ✅ |
| Ollama qwen3:8b | 7 | 11,4 / 15,0 s ❌ | 3,8 s ❌ |

## Consequência
Com 16 GB e uma GPU só, o Whisper (MLX) e um LLM local de 8B disputam a GPU e a memória, e **os dois** ficam lentos. O extrator local continua disponível (privacidade, offline), mas no hardware de referência não cumpre a meta ao vivo. Opções: extrator online como padrão quando houver chave; modelo local menor (3–4B); ou local só para arquivos, que não têm meta de latência.

## Decisão sobre o padrão (2026-10-19)
- **Extrator padrão: OpenAI `gpt-5.4-mini` quando houver chave da OpenAI**; sem chave, Ollama `qwen3:8b`.
- O padrão é calculado a cada leitura enquanto o usuário não salvar as configurações: cadastrar a chave da OpenAI passa a extração para ela. Depois de salvo, vale a escolha do usuário.
- O Ollama segue como opção local nas configurações, com aviso de que ao vivo pode atrasar a transcrição.
