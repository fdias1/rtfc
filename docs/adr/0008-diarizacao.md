# ADR 0008 — Diarização: embedding por frase com sherpa-onnx, sem pyannote

**Status:** aceito · 2026-10-19 · M4

## Contexto
O plano previa sherpa-onnx ao vivo (embedding por trecho e agrupamento incremental) e o pyannote community-1 para arquivos e para o "refinar falantes" no fim da sessão. Ao implementar, três coisas pesaram contra o pyannote:
- o community-1 é um modelo restrito no Hugging Face: exige conta, aceite dos termos e token, o que vai contra a decisão de não depender de contas (como na busca);
- depende de PyTorch em todas as plataformas (hoje ele só vem no macOS, puxado pelo mlx-whisper; no Windows e no Linux seriam ~2 GB a mais no instalador, M9);
- a alternativa sem conta, o pipeline offline do próprio sherpa-onnx (segmentação pyannote 3.0 em ONNX + embedding + agrupamento), foi **mais lenta e menos precisa** no nosso teste: 45 s para 114 s de áudio e 82% dos segmentos certos, contra 100% do método abaixo.

## Decisão
- **Unidade = segmento da transcrição** (uma frase). Cada segmento vira um embedding de falante; o rótulo é do segmento inteiro. Frases com duas pessoas são raras, porque a fala de outra pessoa costuma vir depois de pausa, e pausa fecha o segmento.
- **Modelo:** 3D-Speaker ERes2Net base (`3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx`, Apache-2.0, ~40 MB), rodando no sherpa-onnx (CPU, thread própria). É baixado do GitHub do sherpa-onnx no primeiro uso, sem conta, para `~/.cache/rtfc/models/diarization`. Ganhou do TitaNet small e do WeSpeaker ResNet34 no teste (o WeSpeaker juntou todos num falante só).
- **Ao vivo:** atribuição incremental por similaridade de cosseno com o centróide de cada falante (limiar padrão 0,6, configurável: 0,5/0,6/0,7). Quando dois centróides ficam parecidos com o tempo, os falantes são fundidos e a UI recebe `speakers.updated` com os segmentos remapeados. Trechos com menos de 0,8 s não criam falante (herdam o mais próximo ou o anterior). Custo: ~0,1 s por frase.
- **Fim da sessão (ao vivo e arquivo):** refinamento automático com os embeddings já calculados: parte do agrupamento ao vivo e alterna recalcular centróides, fundir os parecidos e reatribuir cada segmento (estilo k-means), sem recalcular nada.
- **"Refinar falantes"** numa sessão salva: decodifica o áudio, recalcula os embeddings de todos os segmentos e refaz o refinamento (serve também para sessões gravadas com a diarização desligada ou depois de mudar o limiar).
- **Rótulos estáveis:** `S1`, `S2`… no banco; o nome dado pelo usuário fica em `session.json` (`speakers`). O refinamento mapeia os grupos novos para os rótulos antigos com maior sobreposição, então os nomes sobrevivem.
- **Onde aparece o falante:** chip na transcrição quando o falante muda, barra de falantes (renomear com um clique), cards e filtro das checagens, `<v Nome>` no VTT (regravado ao renomear e ao refinar), e nos prompts de extração, contexto e checagem ("QUEM DISSE").
- **Primeiro uso ao vivo:** se o modelo ainda está baixando, a transcrição não espera; os segmentos ficam sem falante e o refinamento do fim os preenche. Em arquivo, espera o modelo.
- **Desligável** nas configurações (Transcrição → "Identificar quem está falando").

## Medições
Debate sintético com 3 vozes pt-BR do macOS (22 falas, 114 s; `eval/diarization/make_debate.py`), transcrito pelo STT padrão (33–34 segmentos), limiar 0,6:

| Áudio | Ao vivo | Refinado |
|---|---|---|
| Limpo | 97% | 100% |
| Degradado (Opus 16 kbps, ruído, eco, banda telefônica) | 94% | 100% |

Ao vivo em tempo real (no M2 Pro, junto com o Whisper): 94% → 100% no áudio degradado, embedding p50 de 106 ms.

**Limitação:** vozes sintéticas são mais fáceis de separar que pessoas reais, e o teste não tem fala sobreposta. O aceite do plano (≥ 85% em arquivo, ≥ 70% ao vivo, num debate real) ainda precisa de um trecho real anotado. Para medir: salvar o áudio e o gabarito `<áudio>.json` (`[{start, end, speaker}]`) e rodar `eval/diarization/run.py`.

## Consequências
- Sem PyTorch nem conta no Hugging Face; +40 MB de modelo e o sherpa-onnx (~20 MB) no app.
- Fala sobreposta e trocas de falante no meio da frase ficam com um rótulo só.
- Se o refinamento não bastar em debates reais, a próxima opção é usar a segmentação pyannote 3.0 (ONNX, sem conta) só para cortar segmentos em trocas de falante, mantendo o embedding por trecho.
