# ADR 0007 — Modelo local como padrão e avaliação dos veredictos (M8)

**Status:** aceito · 2026-10-19

## Contexto
O usuário pediu para trocar o GPT por um modelo local (os créditos estão acabando). O M8 já tinha montado um dataset real: 111 afirmações do 2º turno de 2026 (debates e entrevistas Lula × Flávio Bolsonaro), checadas por Lupa e Aos Fatos, com o selo conferido no próprio artigo (`eval/verdicts/`).

## Decisões
- **Padrão: Ollama `qwen3:8b`** para extração **e** checagem. O `qwen3:14b` fica disponível nas configurações para máquinas com mais memória. Os provedores online também continuam lá.
- **Um modelo só para os dois papéis:** com 16 GB o Ollama dispõe de ~11,8 GB de GPU; o 8B (5,2 GB) e o 14B (9,3 GB) não cabem juntos, e o Ollama recarregaria o modelo a cada troca.
- **`num_ctx` = 12.288 no Ollama.** O padrão é 4.096, e o excesso era cortado pelo começo do prompt, onde estão as instruções. O prompt de veredicto passava disso.
- **Evidência mais enxuta com modelo local** (5 trechos de ~1.100 caracteres), porque o 8B processa ~180 tokens/s de entrada neste Mac.
- **Avaliação com os domínios das agências bloqueados**, para o rtfc não achar a própria checagem.

## Resultados
Extração (texto de referência, nota mínima 4):

| Extrator | Recall | Falsos positivos | Chamada p50 / p90 |
|---|---|---|---|
| OpenAI gpt-5.4-mini | 100% | 0% | ~1 / 1,1 s |
| **Ollama qwen3:8b (padrão)** | **80%** | **0%** | **5,9 / 6,8 s** |
| Ollama qwen3:14b | 100% | 0% | 8,2 / 12,2 s |

Veredictos, na **mesma amostra estratificada de 40** afirmações reais:

| Checador | Concordância exata | Direção | Tempo por checagem (p50 / p90) |
|---|---|---|---|
| OpenAI gpt-5.4-mini | 60% | 70% | ~6 / 8 s |
| OpenAI gpt-5.4 | 52% | 52% | ~10 / 13 s |
| **Ollama qwen3:8b (padrão)** | **32%** | **52%** | **28 / 36 s** |
| Ollama qwen3:14b | 45% | 65% | 64 / 92 s |

No dataset completo (111): gpt-5.4-mini 46% (direção 61%); gpt-5.4 43%. Ninguém chega à meta de 80% do PRD. Pesam três fatores: a busca sem as agências (para eventos recentes, muitas vezes só elas têm o dado consolidado), ruído no dataset (o selo foi extraído por LLM e precisa de revisão humana) e o raciocínio do modelo.

## Lições de calibração (já aplicadas ao prompt)
- Leitura caridosa, como um ouvinte comum entenderia: se algum indicador oficial confirma, é verdadeiro.
- "Fora de contexto" só quando o contexto omitido muda a conclusão; contradição do ponto central é falso.
- Separar quem disse de quem se fala.
- Em citações vale o sentido, não a palavra exata.

## Por que o 8B e não o 14B
O usuário escolheu primeiro o 14B, que acertou mais. No teste ao vivo, porém, ele não coube: com o qwen3:14b carregado (10,2 GB) junto com o Whisper large-v3-turbo, o app e os programas do dia a dia (Docker do SearXNG, editores, chat), o Mac de 16 GB passou a usar **12 GB de swap**, e a transcrição **não produziu nenhuma frase em 105 s**. Sozinho, o 14B funciona; o que falha é ele somado à transcrição em tempo real. O padrão voltou para o 8B, que funciona ao vivo, com veredicto em ~30 s.

## Consequências
- Sem custo e sem enviar texto para fora, mas a checagem local acerta bem menos que um modelo online (32% contra 60% na mesma amostra).
- Ao vivo com o 8B, a extração e o veredicto ficam perto ou acima das metas de latência do PRD, porque dividem a GPU com o Whisper (ADR 0004).
- O ganho de qualidade do 14B pode ser aproveitado **depois da sessão**, quando o Whisper já saiu da memória: é o "rechecar com modelo de qualidade" (próximo passo).
- Requer `ollama pull qwen3:8b` (5,2 GB).

## Próximos passos
- Revisão humana do dataset (o selo foi extraído por LLM e há itens com selo trocado).
- Medir de novo com as agências permitidas, como teto do que a busca permite.
- Testar o modo de raciocínio (`think`) só no checador.
