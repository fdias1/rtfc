# ADR 0006 — Seleção de afirmações, contexto e preferência por fontes primárias

**Status:** aceito · 2026-10-19 · Ajustes pós-M6, pedidos pelo usuário

## Problemas
1. Muitas afirmações genéricas ou impossíveis de checar eram selecionadas ("os hospitais continuam lotados", "o STF decidiu que a lei é constitucional"), e a maioria terminava em "inconclusivo".
2. A checagem via só a frase, sem saber de onde, de quando e de quem ela vinha.
3. O ranking punha checadores e imprensa à frente, o que alimenta viés: a evidência deve ser, sempre que possível, auditável na origem.

## Decisões
- **Contexto do conteúdo** (`SessionInfo.context`): o usuário pode digitá-lo antes de iniciar ou editá-lo depois. Se ficar vazio, o LLM gera um com 6 frases e o atualiza com 40 (sem sobrescrever o do usuário); dá para pedir "Gerar da transcrição" a qualquer momento.
- **Seleção por nota**: o extrator dá nota de 1 a 5 de relevância e checabilidade a cada afirmação, e só as com nota ≥ 4 (configurável: 3, 4 ou 5) são registradas. O prompt explica o que é "específico e relevante". Quando o objeto não é identificável ("a lei", "o projeto", um número sem origem), a nota máxima é 2.
- **Contexto na checagem**: a geração de consultas e o veredicto recebem o contexto do conteúdo, quem disse (quando houver diarização, M4), o contexto da afirmação escrito pelo extrator e a transcrição de ~60 s antes a 15 s depois.
- **Fontes primárias primeiro**:
  - novo tipo `primary`: governo, legislativo, judiciário, estatística, bancos centrais, institutos de pesquisa, universidades, periódicos científicos e organismos internacionais. A Wikipédia passa a contar como "outra";
  - ordem: primárias > checadores > imprensa > outras, com **cota** entre os candidatos (imprensa, checadores e outras: até 3 cada), para que nenhum tipo domine e as outras fontes continuem entrando;
  - a primeira consulta mira a fonte primária que detém o dado;
  - PDFs (relatórios e notas técnicas) passam a ser lidos (`pypdf`);
  - no veredicto, a fonte primária prevalece em conflitos, e com só imprensa a confiança fica em no máximo 0,6.
- **Robustez da busca**:
  - os buscadores bloqueavam rajadas (CAPTCHA, "too many requests"): agora há no máximo 2 consultas simultâneas, 0,4 s entre elas, cache de 1 h, 3 consultas por afirmação e mais motores no SearXNG;
  - **busca sem resultado vira erro** ("rechecar"), nunca "inconclusivo", que seria enganoso.
- **Saída do LLM em outro alfabeto** (ex.: "nome do বক্তা") volta para correção.

## Efeito medido (mesmo discurso de referência, OpenAI gpt-5.4-mini)
| | Antes | Depois |
|---|---|---|
| Afirmações extraídas | 11 (várias genéricas) | 6 |
| Recall das afirmações específicas | 100% | 100% |
| Falsos positivos (opinião/promessa) | 0% | 0% |
| Fontes por checagem | variável | 3–4, maioria primária (11 primárias, 6 imprensa, 2 outras) |
| Fala → veredicto (p90, ao vivo) | 17,8 s | 15,8 s |
