# rtfc — Real Time Fact Checker

**PRD v1.0** · 2026-10-19 · Status: fechado

---

## 1. Visão

O rtfc é um app desktop livre e open source. Ele ouve discursos, conversas, vídeos e transmissões, transcreve tudo localmente, identifica as afirmações factuais verificáveis e checa cada uma contra fontes públicas na internet. Para cada afirmação devolve um veredicto claro (**Verdadeiro**, **Fora de contexto**, **Falso** ou **Inconclusivo**), com justificativa, nível de confiança e os links das fontes analisadas.

**Objetivo final:** permitir que jornalistas e o público em geral chequem qualquer áudio, vídeo ou discurso ao vivo.
**Objetivo do MVP:** uma ferramenta funcional de uso pessoal (do autor), com arquitetura pronta para distribuição futura.

## 2. Princípios

1. **Privacidade e offline primeiro.** Captura, transcrição, detecção de fala e diarização rodam sempre localmente. Só a busca (e, opcionalmente, o LLM) usam a rede.
2. **Agnóstico de fornecedor.** Nenhum LLM nem provedor de busca é obrigatório. Tudo é plugável.
3. **Busca própria.** O rtfc faz a pesquisa e entrega as evidências ao LLM. Não usamos a busca nativa dos fornecedores de LLM, para evitar o viés deles e garantir o mesmo comportamento com qualquer modelo.
4. **Sem evidência, sem veredicto.** O LLM só pode citar fontes que o próprio rtfc recuperou. Se a evidência for insuficiente, o veredicto é "Inconclusivo".
5. **Transparência.** Todo veredicto mostra a justificativa, as fontes e a confiança. O usuário sempre vê que o resultado foi gerado por IA.
6. **Gratuito e de código aberto (source-available).** Licença **PolyForm Noncommercial 1.0.0**: o código é público e pode ser usado, estudado e modificado, mas é proibido qualquer uso comercial, inclusive cobrar pelo app. Não é software livre segundo a FSF/OSI; foi uma escolha consciente (ver §11).

## 3. Público e personas

| Fase | Persona | Necessidade |
|---|---|---|
| MVP | Autor (dev, técnico) | Validar o pipeline com debates, entrevistas e podcasts; configurar modelos e chaves livremente |
| Futuro | Jornalista / checador | Checar ao vivo durante debates e entrevistas, exportar relatório com fontes, revisar e corrigir veredictos |
| Futuro | Público em geral | Colar um vídeo ou ouvir uma live e ver o que é verdade, sem configurar nada |

## 4. Escopo

### 4.1 MVP (dentro do escopo)

**Entradas de áudio (todas no MVP):**
- **Microfone** (ao vivo).
- **Áudio do sistema** (ao vivo): qualquer som tocando no computador, como uma live do YouTube, um podcast ou uma chamada.
- **Arquivo de áudio** (mp3, wav, m4a, ogg, flac…).
- **Arquivo de vídeo** (mp4, mkv, mov, webm…): o áudio é extraído com ffmpeg, e o vídeo é exibido no app sincronizado com a transcrição.

**Processamento:**
- Transcrição local com Whisper, em streaming para as fontes ao vivo e em lote acelerado para arquivos.
- Identificação de interlocutores (diarização) local.
- Extração automática de afirmações factuais verificáveis, por LLM local **ou** online (configurável).
- Checagem de cada afirmação: geração de consultas, busca web própria, leitura das páginas, análise pelo LLM e veredicto com fontes.
- Idioma configurável (padrão pt-BR). A checagem acontece **no mesmo idioma do discurso**: consultas, fontes preferidas e justificativa.

**Interface:**
- Transcrição em tempo real com interlocutor e timestamp.
- Afirmações destacadas na transcrição, com cor por veredicto e ligação bidirecional: clicar no trecho abre o card do resultado e clicar no card rola até o trecho.
- Cards de checagem com estado (na fila, verificando, concluído, cancelado, erro), veredicto, confiança, justificativa e fontes.
- **Selecionar um trecho qualquer da transcrição e mandar verificar manualmente.**
- **Cancelar uma verificação em andamento** ou **descartar uma já concluída**.
- Rechecar uma afirmação.
- Para vídeo e arquivo: player sincronizado; clicar numa afirmação leva ao instante dela.

**Dados e configuração:**
- Histórico de sessões local (SQLite): transcrição, afirmações, veredictos, fontes e metadados.
- **Gravação integral do áudio** de toda sessão ao vivo, com a transcrição alinhada por tempo (SRT/WebVTT) para encontrar qualquer ponto da gravação.
- Exportação em Markdown, JSON, SRT e WebVTT.
- Chaves de API próprias do usuário (BYOK), guardadas no cofre do sistema operacional.
- Tela de configurações: modelo de STT, dispositivo (CPU/GPU), LLM de extração, LLM de checagem, provedor de busca, idioma, listas de domínios.

### 4.2 Fora do MVP (roadmap)

| Fase | Itens |
|---|---|
| v1.1 | Ingestão por URL (YouTube, podcasts) via yt-dlp; exportação em PDF; edição manual do veredicto e da justificativa pelo usuário |
| v2 — Distribuição | Instaladores assinados (macOS notarizado, Windows assinado, AppImage/deb), auto-update, onboarding, gerenciador de download de modelos |
| v2 — Conta rtfc | Backend opcional ("proxy rtfc") que permite usar o app sem chave própria, com limites de uso e financiamento a definir; fundamental para o público em geral |
| v3 | Modo legenda/overlay sobre qualquer janela, extensão de navegador, colaboração entre checadores, base compartilhada de checagens já feitas |

### 4.3 Não-objetivos

- Checar opiniões, promessas, previsões ou juízos de valor.
- Ser a fonte da verdade: o rtfc é uma ferramenta de apoio e mostra evidências para o usuário julgar.
- Controle de custos de API no MVP (decisão explícita: não haverá limite de gasto nem contador).

## 5. Requisitos funcionais

### RF1 — Captura e ingestão
- **RF1.1** Listar e selecionar o microfone.
- **RF1.2** Capturar o áudio do sistema no macOS (13+), Windows (10/11) e Linux (PipeWire/PulseAudio).
- **RF1.3** Abrir arquivos de áudio e vídeo (arrastar e soltar, ou seletor) e extrair o áudio com ffmpeg empacotado no app.
- **RF1.4** Normalizar todas as fontes para PCM mono 16 kHz antes do pipeline, que é único para todas.
- **RF1.5** Pausar, retomar e encerrar uma sessão ao vivo.

### RF2 — Transcrição (STT)
- **RF2.1** Transcrever localmente com Whisper, com o modelo escolhível (tiny → large-v3-turbo).
- **RF2.2** Ao vivo: segmentação por VAD (Silero), texto parcial ("provisório") seguido do texto confirmado.
- **RF2.3** Arquivos: processamento em lote, mais rápido que o tempo real quando o hardware permitir, com barra de progresso.
- **RF2.4** Idioma configurável ou detecção automática. O idioma detectado ou escolhido se propaga para a checagem.
- **RF2.5** Timestamps por segmento (e por palavra, quando disponível).

### RF3 — Diarização (interlocutores)
O Whisper **não** identifica interlocutores sozinho. A diarização é uma etapa separada e plugável (ver §7.4).
- **RF3.1** Rotular segmentos como "Falante 1, 2…".
- **RF3.2** Permitir renomear falantes ("Falante 1" → "Candidato X"). O nome aparece na transcrição e no relatório.
- **RF3.3** A diarização pode ser desativada (para quem tem hardware fraco ou fala de uma pessoa só).

### RF4 — Extração de afirmações
- **RF4.1** Um LLM (local ou online, configurável) é acionado **a cada frase confirmada**, recebendo as frases novas mais o contexto anterior, e extrai **somente afirmações factuais verificáveis**: números, estatísticas, datas, eventos, citações e atribuições ("X fez/disse Y").
- **RF4.2** Cada afirmação é **reescrita de forma autocontida** (resolvendo "ele", "isso", "aquele ano" pelo contexto), mas mantém a ligação com o trecho original (offsets e timestamps) e com o falante.
- **RF4.5** Contexto do conteúdo (digitado pelo usuário ou gerado pelo LLM) guia a seleção; só afirmações específicas e relevantes, com nota ≥ 4 de 5, são registradas (ADR 0006).
- **RF4.3** Deduplicação: afirmações equivalentes já checadas na sessão reaproveitam o resultado.
- **RF4.4** Seleção manual: o usuário seleciona um trecho e escolhe "Verificar". O trecho passa pela normalização do RF4.2 e entra na fila com prioridade.

### RF5 — Checagem
- **RF5.1** Fila assíncrona com concorrência configurável. Cada item pode ser cancelado a qualquer momento (a requisição ao LLM ou à busca é abortada).
- **RF5.2** Pipeline por afirmação:
  1. gerar de 2 a 4 consultas de busca no idioma do discurso;
  2. buscar no provedor configurado;
  3. ranquear os resultados, dando prioridade às agências de checagem e fontes oficiais e removendo os domínios bloqueados;
  4. baixar as páginas e extrair o texto principal;
  5. o LLM avalia as evidências e devolve um JSON estruturado.
- **RF5.3** Saída estruturada e validada por schema:
  ```json
  {
    "verdict": "verdadeiro | fora_de_contexto | falso | inconclusivo",
    "confidence": 0.0,
    "justification": "1 a 3 frases",
    "sources": [{ "url": "...", "title": "...", "stance": "apoia | refuta | contextualiza", "quote": "trecho relevante" }]
  }
  ```
- **RF5.4** **Regras de integridade** (aplicadas por código, não só pelo prompt):
  - cada URL citada precisa existir no conjunto recuperado; citações inventadas são descartadas;
  - se, depois da validação, sobrarem menos de **2 fontes**, o veredicto é forçado para "Inconclusivo";
  - a data do discurso (ou "agora", ao vivo) é informada ao LLM para lidar com afirmações temporais.
- **RF5.5** Rechecar sob demanda (por exemplo, depois de trocar o modelo).

### RF6 — Interface
- **RF6.1** Layout em três áreas: controles da fonte (e player de vídeo, quando houver), transcrição ao vivo e painel de checagens.
- **RF6.2** Destaques na transcrição com cor por estado e veredicto; o clique sincroniza com o card.
- **RF6.3** Card de checagem: afirmação, falante, timestamp, veredicto (com cor e ícone, legível também para daltônicos), barra de confiança, justificativa, fontes (título, domínio, posição e trecho citado) e ações (cancelar, descartar, rechecar).
- **RF6.4** Filtros: por veredicto, por falante e "só pendentes".
- **RF6.5** Aviso permanente: "Veredictos gerados por IA — confira as fontes."
- **RF6.6** Interface em pt-BR, com i18n preparado.

### RF7 — Sessões, gravação e exportação
- **RF7.1** Toda sessão é salva automaticamente e pode ser reaberta.
- **RF7.2** **Gravação integral do áudio** das sessões ao vivo (microfone e sistema), gravada em disco continuamente (sem perder o que já foi gravado se o app fechar), em Opus/OGG mono 48 kHz (~30 MB por hora). Nas sessões de arquivo, o app guarda o caminho do original e, opcionalmente, uma cópia.
- **RF7.3** **Transcrição alinhada com a gravação.** A fonte da verdade fica no SQLite, com timestamps por segmento e por palavra. Dela saem:
  - **SRT**: legenda universal, abre em qualquer player junto com o áudio ou vídeo;
  - **WebVTT**: o mesmo, com o nome do falante (`<v Falante 1>`);
  - afirmações e veredictos também carregam o timestamp, então o relatório aponta o instante exato.
- **RF7.4** Ao reabrir uma sessão, o player toca a gravação sincronizada com a transcrição: clicar num trecho ou numa afirmação pula para aquele instante.
- **RF7.5** Exportação em Markdown (relatório legível), JSON (dados completos), SRT e WebVTT.
- **RF7.6** Pasta de sessões configurável; cada sessão é uma pasta com `audio.ogg`, `transcricao.srt`, `transcricao.vtt` e `sessao.json`, para ser usada fora do app.

### RF8 — Configuração
- **RF8.1** Provedores de LLM, separados para **extração** e **checagem**, cada um apontando para qualquer modelo: Gemini, Claude, OpenAI, DeepSeek, Mistral, ou um modelo local via Ollama ou llama.cpp.
- **RF8.2** Provedor de busca plugável (ver §7.6).
- **RF8.3** Chaves no cofre do SO (Keychain no macOS, Credential Manager no Windows, Secret Service no Linux).
- **RF8.4** Listas de domínios priorizados e bloqueados, editáveis.
- **RF8.5** Botão "testar conexão" para cada provedor.

## 6. Requisitos não funcionais

| ID | Requisito | Meta |
|---|---|---|
| RNF1 | Latência da transcrição ao vivo (fala → texto confirmado) | ≤ 3 s no hardware de referência |
| RNF2 | Latência da extração (texto confirmado → afirmação na UI) | ≤ 5 s (p90) com LLM online |
| RNF2a | Latência da checagem (afirmação extraída → veredicto) | ≤ 30 s (p90) com LLM online |
| RNF2b | **Latência de ponta a ponta (fala → veredicto na UI)** | **≤ 35 s (p90)** ao vivo, com LLM online, no hardware de referência |
| RNF3 | Plataformas | macOS 13+ (Apple Silicon prioritário, Intel se viável), Windows 10/11 x64, Linux x64 (Ubuntu 22.04+) |
| RNF4 | Offline | Captura, STT, VAD e diarização funcionam sem internet; com LLM local, só a busca usa a rede |
| RNF5 | Hardware mínimo | **16 GB de RAM**; GPU recomendada (Apple Silicon ou NVIDIA/CUDA), com fallback em CPU usando modelos menores |
| RNF5a | Hardware de referência | **MacBook Apple M2 Pro, 16 GB, 10 núcleos de CPU, 16 de GPU, macOS 26**. Todas as metas de desempenho são medidas nele |
| RNF6 | Privacidade | Nenhum áudio sai da máquina. Só vão para a rede o texto das afirmações (para o LLM e a busca) e as URLs baixadas |
| RNF7 | Robustez | Falha de um provedor não derruba a sessão: a afirmação fica em "erro" com opção de tentar de novo |
| RNF8 | Extensibilidade | Adicionar um novo provedor de STT, LLM ou busca = implementar uma interface, sem mexer no pipeline |
| RNF9 | Licenciamento | Licença PolyForm Noncommercial 1.0.0. Dependências só com licenças permissivas (MIT, BSD, Apache-2.0) ou LGPL com ligação dinâmica (ffmpeg em build LGPL). **Proibidas dependências GPL/AGPL** (incompatíveis). Licenças dos modelos (pesos) documentadas em `THIRD_PARTY.md` |

## 7. Arquitetura de alto nível

### 7.1 Stack escolhida

| Camada | Escolha | Por quê |
|---|---|---|
| Shell desktop | **Electron + electron-vite + React + TypeScript** | Seu background é Node/React, então não precisa aprender Rust. O ponto decisivo: o `desktopCapturer` do Electron captura **o áudio do sistema** (loopback) no macOS (via ScreenCaptureKit) e no Windows sem código nativo. No Tauri isso exigiria plugins em Rust específicos para cada SO. O tamanho maior do Electron é irrelevante perto dos modelos Whisper (centenas de MB a GB) |
| UI | React + Tailwind + Zustand | Familiar e produtivo |
| Backend | **Python 3.12** como processo sidecar, **FastAPI + WebSocket** em localhost | Melhor ecossistema de IA (Whisper, pyannote, LiteLLM). Empacotado com PyInstaller |
| STT | faster-whisper (padrão) / mlx-whisper (Apple Silicon) | faster-whisper roda em CPU e CUDA em todas as plataformas; MLX usa a GPU do Apple Silicon |
| VAD | Silero VAD | Leve e offline |
| Diarização | ver §7.4 | — |
| LLM | **LiteLLM** + validação com Pydantic | Uma interface para mais de 100 provedores, incluindo Ollama (local) |
| Busca | Camada própria plugável; **SearXNG local** como padrão, DuckDuckGo de reserva, Tavily opcional (§7.6) | Evita viés dos fornecedores de LLM e não exige conta (ADR 0005) |
| Extração de páginas | httpx + trafilatura (ou o conteúdo da Tavily, quando usada) | Texto principal de artigos |
| Persistência | SQLite (SQLAlchemy/SQLModel) | Local e simples |
| Segredos | `keyring` (Python) | Cofre nativo nos 3 SOs |
| Mídia | ffmpeg empacotado | Extrair o áudio de vídeos, decodificar formatos e gravar Opus |

### 7.2 Fluxo de dados

```
┌──────────────────────── Electron ────────────────────────┐
│  Renderer (React)                                        │
│   ├─ Mic: getUserMedia ─┐                                │
│   ├─ Sistema: getDisplayMedia(loopback) ─┤ AudioWorklet  │
│   │                                     └─► PCM 16k mono │
│   ├─ Player de vídeo (arquivo local)                     │
│   └─ UI: transcrição · destaques · cards                 │
│  Main (Node): spawn/supervisão do sidecar, IPC, arquivos │
└───────────────┬──────────────────────────────────────────┘
                │ WebSocket (áudio binário + eventos JSON)
┌───────────────▼──────────── Python sidecar ──────────────┐
│ Ingestão ─► VAD ─► STT (streaming/lote) ─► Diarização    │
│                         │                                │
│                         ▼                                │
│              Transcrição confirmada (+ falante, ts)      │
│                         │                                │
│                         ▼                                │
│            Extrator de afirmações (LLM local/online)     │
│                         │          ▲ seleção manual (UI) │
│                         ▼                                │
│   Fila de checagem (async, cancelável, dedup)            │
│     consultas ─► busca ─► ranking ─► fetch/extract       │
│     ─► LLM veredicto ─► validação de integridade         │
│                         │                                │
│                         ▼                                │
│        SQLite (sessões)  ·  eventos ─► UI                │
└──────────────────────────────────────────────────────────┘
```

- **Ao vivo** (microfone ou sistema): a captura acontece no renderer, e o PCM é enviado em blocos pelo WebSocket.
- **Arquivos**: o main passa o caminho ao sidecar, que decodifica com ffmpeg. Assim um arquivo de 2 h não trafega pelo WebSocket.
- **Linux, áudio do sistema**: o loopback do Electron é limitado. Alternativa: o sidecar captura o *monitor source* do PipeWire/PulseAudio via ffmpeg ou `soundcard`.

### 7.3 Protocolo UI ↔ sidecar (eventos)

`session.start/stop/pause` · `audio.chunk` · `transcript.partial` · `transcript.final` · `speaker.update` · `claim.detected` · `check.queued/progress/done/error/cancelled` · `claim.manual` · `check.cancel` · `check.discard` · `check.retry`

### 7.4 Diarização: opções

O Whisper não faz diarização. Alternativas avaliadas:

| Opção | Ao vivo | Arquivo | Prós | Contras |
|---|---|---|---|---|
| **pyannote.audio** (community-1 / 3.x) | Fraco | **Excelente** | Estado da arte, offline depois de baixar | Pesos com acesso controlado no Hugging Face (exige aceitar os termos uma vez); pesado em CPU |
| **diart** (sobre pyannote) | **Bom** | — | Feito para streaming, clustering incremental | Projeto menos ativo, mais latência |
| **sherpa-onnx** (speaker diarization) | Bom | Bom | ONNX leve, multiplataforma, sem PyTorch, licença Apache-2.0 | Precisão um pouco menor |
| WhisperX | — | Muito bom | Junta Whisper, alinhamento por palavra e pyannote | Só lote; mesma dependência do pyannote |
| NVIDIA NeMo (Sortformer) | Bom | Muito bom | Ótima precisão | Pesado, voltado para CUDA |

**Recomendação para o MVP:** interface `Diarizer` plugável.
- **Arquivo:** pyannote (melhor qualidade).
- **Ao vivo:** sherpa-onnx com embeddings de falante e clustering incremental (leve e multiplataforma).
- Ao fim de uma sessão ao vivo, opção de "refinar falantes" com pyannote sobre o áudio gravado (possível porque toda sessão é gravada, ver RF7.2).

### 7.5 Camada de LLM (agnóstica)

- Interface `LLMClient.complete(messages, schema, cancel_token)` implementada via LiteLLM.
- Dois papéis configuráveis de forma independente: `extractor` e `checker` (por exemplo, extrator local via Ollama e checador Claude/Gemini/GPT/DeepSeek).
- Saída estruturada: usa JSON mode ou tool-calling quando o modelo suporta; senão, prompt com schema, parse e até 2 tentativas de correção.
- Os prompts ficam versionados em arquivos, com placeholders de idioma e data.
- Preparado para o futuro "proxy rtfc": basta mais um provedor que aponta para o backend próprio.

### 7.6 Camada de busca (própria)

- Interface `SearchProvider.search(query, lang, n) -> [Result]`.
- **Padrão do MVP: SearXNG local** (software livre via Docker, sem conta), com **reserva automática no DuckDuckGo** e **Tavily opcional** (com chave). O texto das páginas é extraído pelo próprio rtfc (httpx + trafilatura). Ver ADR 0005.
- Ranking (ADR 0006): **fontes primárias auditáveis primeiro** (órgãos oficiais, institutos de pesquisa e estatística, universidades, organismos internacionais), depois agências de checagem, imprensa e demais, com cota por tipo. Listas anteriores: (1) agências de checagem do idioma (pt-BR: Lupa, Aos Fatos, Estadão Verifica, AFP Checamos, Fato ou Fake, Comprova, Boatos.org), (2) fontes oficiais (IBGE, TSE, gov.br, Diário Oficial, Banco Central…), (3) veículos jornalísticos, (4) demais. As listas são configuráveis e têm um conjunto padrão por idioma.

### 7.7 Veredictos

| Veredicto | Significado |
|---|---|
| ✅ **Verdadeiro** | As evidências confirmam a afirmação |
| ⚠️ **Fora de contexto / Depende** | Parcialmente verdadeira, exagerada, desatualizada ou enganosa pela omissão de contexto |
| ❌ **Falso** | As evidências contradizem a afirmação |
| ❔ **Inconclusivo** | Evidência insuficiente ou contraditória (sempre que houver menos de 2 fontes válidas) |

Cada veredicto vem com uma **confiança** de 0 a 1 (exibida como baixa, média ou alta), uma **justificativa** de 1 a 3 frases e as **fontes** com posição (apoia, refuta, contextualiza) e trecho citado.

## 8. Identidade visual

**Direção:** simples, clara e calma. Deve transmitir **confiança** (sóbria, jornalística, sem alarmismo) e **leveza** (muito espaço em branco, poucos elementos). No MVP só existe o tema claro.

| Token | Cor | Uso |
|---|---|---|
| `primary` | **#0E5A6B** (azul petróleo) | Marca, botões principais, links, foco |
| `primary-strong` | #0A4352 | Hover, cabeçalho, texto de destaque |
| `primary-soft` | #E3F0F2 | Fundos de seleção, chips, destaque de trecho em verificação |
| `bg` | #F7FAFA | Fundo do app |
| `surface` | #FFFFFF | Cards e painéis |
| `border` | #D9E3E5 | Divisórias |
| `text` | #1C2B30 | Texto principal |
| `text-muted` | #5E7177 | Metadados, timestamps |
| `verdict-true` | #2F7D5C (verde sóbrio) | Verdadeiro |
| `verdict-context` | #B7791F (âmbar) | Fora de contexto |
| `verdict-false` | #B4413A (vermelho tijolo, não alarmista) | Falso |
| `verdict-inconclusive` | #6B7C82 (cinza azulado) | Inconclusivo |

- **Tipografia:** Inter na interface e JetBrains Mono nos timestamps, as duas open source e embutidas no app. A transcrição usa corpo de 16 a 17 px e entrelinha generosa, para leitura longa.
- **Forma:** cantos levemente arredondados (8 px), sombras quase imperceptíveis, ícones de traço fino (Lucide).
- **Acessibilidade:** o veredicto nunca depende só da cor (sempre tem ícone e rótulo); contraste AA em todo texto.
- **Logo (provisório):** a palavra "rtfc" em minúsculas, em azul petróleo, com um sinal de check discreto. Nome definitivo fica para a v2.

## 9. Métricas de sucesso (MVP)

- **Precisão do veredicto** ≥ 80% de concordância com a checagem humana num conjunto de avaliação de cerca de 100 afirmações já checadas por agências brasileiras.
- **Recall da extração** ≥ 70% das afirmações verificáveis de um discurso anotado manualmente, com no máximo 20% de falsos positivos (opiniões tratadas como fatos).
- **Zero URLs alucinadas** nos veredictos (garantido pela validação).
- Latências do RNF1, RNF2, RNF2a e RNF2b atingidas no hardware de referência (M2 Pro, 16 GB).
- Uma sessão contínua de 2 h ao vivo sem travar nem vazar memória.

## 10. Riscos e mitigações

| Risco | Impacto | Mitigação |
|---|---|---|
| Alucinação do LLM ou veredicto errado | Alto (credibilidade, risco jurídico) | Integridade das fontes no código, mínimo de 2 fontes, "Inconclusivo" como saída segura, aviso de IA, conjunto de avaliação |
| Afirmações sobre fatos muito recentes, ainda sem cobertura | Médio | Data do discurso no prompt; "Inconclusivo" com a explicação "sem cobertura ainda" |
| Captura do áudio do sistema varia por SO | Médio | Electron no macOS e no Windows, fallback em Python no Linux; testar cedo (spike na semana 1) |
| Desempenho de STT e diarização em CPU fraca | Médio | Modelos menores, diarização opcional, detecção de hardware com sugestão de configuração |
| Viés de fontes ou do provedor de busca | Médio | Busca própria, vários provedores, listas configuráveis e transparentes |
| Bloqueio ou paywall ao baixar páginas | Baixo/Médio | Usar o snippet como evidência fraca; ignorar a fonte se não houver texto |
| Licenças dos pesos (pyannote com acesso controlado) | Baixo | Documentar; sherpa-onnx como alternativa sem restrição |
| Empacotar Python com PyTorch/CTranslate2 em 3 SOs | Médio | PyInstaller por plataforma via CI; modelos baixados sob demanda, fora do instalador |
| Espaço em disco das gravações | Baixo | Opus (~30 MB/h); tamanho por sessão visível; apagar sessões pela UI |
| Busca depende de buscadores de terceiros (via SearXNG/DuckDuckGo), que podem limitar o acesso | Médio | Vários motores agregados, reserva automática, Tavily opcional; interface plugável |

## 11. Decisões e questões em aberto

**Decididas:**
- Gravação integral do áudio + transcrição alinhada (SRT/WebVTT), ver RF7.
- Hardware de referência: M2 Pro, 16 GB (mínimo de 16 GB de RAM).
- Busca padrão: SearXNG local + DuckDuckGo de reserva; Tavily opcional (ADR 0005).
- Identidade visual: §8.

- **Licença: PolyForm Noncommercial 1.0.0.** Consequências aceitas:
  - não é software livre/open source pelas definições da FSF/OSI;
  - uso pessoal, por pesquisa, educação, ONGs e órgãos públicos é permitido; **veículos de imprensa com fins lucrativos precisam de permissão do autor**, que pode concedê-la gratuitamente (licença separada caso a caso, ou uma exceção pública no futuro);
  - dependências GPL ficam proibidas (RNF9).

**Em aberto:**
1. Nome e identidade visual definitivos (v2).
