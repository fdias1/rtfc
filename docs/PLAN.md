# rtfc — Plano de implementação do MVP

**v1.0** · 2026-10-19 · Base: [PRD v1.0](PRD.md)

O MVP está dividido em 10 marcos (M0–M9). Cada um termina com algo que **roda e pode ser demonstrado**, e cada critério de aceite é verificável. Os riscos maiores ficam no começo: captura do áudio do sistema e latência do Whisper (M1, M2).

---

## 1. Estrutura do repositório

Monorepo com dois "mundos", Node e Python, e um contrato compartilhado entre eles.

```
rtfc/
├─ apps/
│  └─ desktop/                 # Electron + electron-vite + React + TS
│     ├─ src/main/             # processo main: janela, sidecar, IPC, captura (permissões)
│     ├─ src/preload/          # ponte segura (contextBridge)
│     └─ src/renderer/         # React: UI, AudioWorklet, cliente WebSocket
├─ backend/                    # Python 3.12, gerenciado com uv
│  ├─ src/rtfc/
│  │  ├─ api/                  # FastAPI: HTTP (config, sessões) + WebSocket (stream/eventos)
│  │  ├─ audio/                # ingestão, ffmpeg, gravação Opus, VAD
│  │  ├─ stt/                  # interface STTEngine + faster-whisper, mlx-whisper
│  │  ├─ diarization/          # interface Diarizer + sherpa-onnx, pyannote
│  │  ├─ llm/                  # LLMClient (LiteLLM), prompts versionados
│  │  ├─ claims/               # extrator, normalização, dedup
│  │  ├─ search/               # SearchProvider + Tavily, ranking, fetch fallback
│  │  ├─ factcheck/            # fila, pipeline, regras de integridade
│  │  ├─ storage/              # SQLite (SQLModel), pasta da sessão, export SRT/VTT/MD/JSON
│  │  ├─ config/               # settings, keyring
│  │  └─ protocol/             # modelos Pydantic dos eventos (fonte do contrato)
│  ├─ prompts/                 # *.md com placeholders {lang} {date}
│  └─ tests/
├─ packages/
│  └─ protocol/                # tipos TS gerados a partir do JSON Schema do backend
├─ eval/                       # datasets e scripts de avaliação (M8)
├─ docs/                       # PRD, PLAN, ADRs
├─ LICENSE                     # PolyForm Noncommercial 1.0.0
└─ THIRD_PARTY.md              # licenças de dependências e modelos
```

**Ferramentas**
- **Node:** pnpm, TypeScript strict, ESLint + Prettier, Vitest, Playwright (E2E do Electron).
- **Python:** uv, ruff, mypy, pytest + pytest-asyncio.
- **Contrato:** Pydantic → JSON Schema → `json-schema-to-typescript`. Os tipos ficam idênticos dos dois lados e um script do CI falha se estiverem desatualizados.
- **CI:** GitHub Actions com lint, testes e checagem de licenças (`pip-licenses` e `license-checker` bloqueiam GPL/AGPL).

## 2. Modelo de dados (SQLite)

```
Session   id, title, source_type(mic|system|file_audio|file_video), source_path,
          language, started_at, ended_at, audio_path, status
Speaker   id, session_id, label("Falante 1"), display_name
Segment   id, session_id, speaker_id, start_ms, end_ms, text, is_final
Word      id, segment_id, start_ms, end_ms, text, prob
Claim     id, session_id, speaker_id, origin(auto|manual), source_text,
          normalized_text, char_start, char_end, start_ms, end_ms,
          status(queued|checking|done|cancelled|discarded|error), dedup_of
Check     id, claim_id, verdict, confidence, justification, model, search_provider,
          created_at, raw_json
Source    id, check_id, url, title, domain, tier(factchecker|official|press|other),
          stance(apoia|refuta|contextualiza), quote
```

Cada sessão também tem uma pasta: `sessions/<id>/{audio.ogg, transcricao.srt, transcricao.vtt, sessao.json}`.

## 3. Marcos

### M0 — Fundação · tamanho P
- `git init`, licença (PolyForm NC 1.0.0), README, THIRD_PARTY.md, `.editorconfig`.
- Scaffold electron-vite (React + TS) e backend com uv + FastAPI.
- **Ciclo de vida do sidecar:** o main faz o spawn do Python numa porta livre com um token aleatório (o WebSocket só aceita esse token), faz o health check, reinicia se cair e o encerra junto com o app. Em dev roda com `uv run`; empacotado, roda o binário PyInstaller (M9).
- Protocolo base: `hello`, `ping` e um evento de exemplo, com os tipos TS gerados.
- Design tokens do PRD §8 no Tailwind, fontes Inter e JetBrains Mono embutidas, layout vazio em três áreas.
- CI básico.

**Aceite:** `pnpm dev` abre o app, o sidecar sobe sozinho, a UI mostra "backend conectado", e matar o Python reconecta automaticamente.

### M1 — Captura e gravação de áudio (spike de risco) · tamanho M
- **Renderer:** `getUserMedia` para o microfone; `getDisplayMedia` com áudio loopback para o sistema, liberado no main com `session.setDisplayMediaRequestHandler({ audio: 'loopback' })`. Inclui as permissões de microfone e de gravação de tela no macOS.
- **AudioWorklet:** downmix para mono, reamostragem para 16 kHz, Int16, blocos de ~100 ms enviados como binário no WebSocket.
- **Sidecar:** recebe o PCM e grava continuamente em `audio.ogg` (pipe para o ffmpeg com libopus, 48 kHz… ou 16 kHz se a qualidade bastar; decidir no spike). Em paralelo, mantém um ring buffer para o pipeline.
- **Arquivos:** o main abre o seletor ou recebe o drag-and-drop e envia o caminho ao sidecar. O ffmpeg decodifica para PCM 16 kHz; no vídeo, o player usa o arquivo original.
- VU meter na UI e seletor de dispositivo.
- Spike **Linux:** testar o loopback do Electron; se falhar, capturar o monitor do PulseAudio/PipeWire via ffmpeg no sidecar.

**Aceite (no M2 Pro):** gravar 10 min de uma live do YouTube pelo áudio do sistema e 10 min de microfone; os `audio.ogg` tocam inteiros e sem falhas; fechar o app à força no meio mantém o áudio gravado até ali.

### M2 — Transcrição (STT) · tamanho G
- Interface `STTEngine` com `transcribe_stream()` e `transcribe_file()`. Implementações: **faster-whisper** (CPU/CUDA) e **mlx-whisper** (Metal).
- **Benchmark no M2 Pro** (script em `eval/`): `small`, `medium` e `large-v3-turbo` em cada motor, medindo latência, RTF e WER num áudio pt-BR de referência. O resultado define o padrão por plataforma e vira um ADR.
- **Streaming:** Silero VAD fecha os segmentos; o texto parcial é emitido a cada ~1 s e confirmado pela política *LocalAgreement* (o texto só é confirmado quando 2 passadas concordam), como no whisper_streaming. Prompt de contexto com as últimas frases confirmadas.
- **Arquivos:** lote com progresso, timestamps por palavra.
- Idioma configurável ou detecção automática, propagado para a sessão.
- Persistência de Segment e Word; geração incremental de **SRT/VTT** na pasta da sessão.
- Download de modelos sob demanda (Hugging Face Hub), com progresso na UI.

**Aceite:** a latência fala → texto confirmado é ≤ 3 s (p90) ao vivo no M2 Pro; um podcast de 1 h é transcrito mais rápido que o tempo real; o SRT abre no VLC sincronizado com o `audio.ogg`.

### M3 — UI de transcrição e sessões · tamanho M
- Transcrição ao vivo: texto parcial em cinza, confirmado em preto, timestamp em mono e rótulo do falante; autoscroll que pausa quando o usuário rola a tela.
- **Player sincronizado** (áudio gravado ou vídeo original): clicar num trecho faz seek, e a reprodução destaca a palavra ou o segmento atual.
- Lista de sessões (abrir, renomear, apagar com confirmação, tamanho em disco).
- Tela de configurações (esqueleto) e estado global com Zustand.
- Seleção de texto na transcrição mapeada para offsets e timestamps (base do RF4.4).

**Aceite:** reabrir uma sessão antiga, clicar em qualquer frase e ouvir o ponto exato da gravação; selecionar um trecho mostra o menu de ação (ainda inativo).

### M4 — Diarização · tamanho M
- Interface `Diarizer`.
- **Ao vivo — sherpa-onnx:** embedding por segmento VAD e clustering incremental por similaridade de cosseno com limiar configurável. Emite `speaker.update` e permite reatribuir falantes retroativamente.
- **Arquivo — pyannote** (community-1): diarização completa, cruzada com os timestamps das palavras (falante = maior sobreposição).
- "Refinar falantes" no fim da sessão ao vivo: roda pyannote sobre `audio.ogg` e remapeia os rótulos.
- Renomear falantes na UI, refletido no VTT (`<v Nome>`).
- Opção de desligar a diarização.

**Aceite:** num trecho de debate com 2 a 3 pessoas, ≥ 85% dos segmentos com o falante certo (arquivo) e ≥ 70% (ao vivo); renomear um falante atualiza a UI e o VTT.

### M5 — Camada de LLM e extração de afirmações · tamanho M
- `LLMClient` sobre LiteLLM: saída estruturada (JSON schema/tools quando houver suporte; senão parse com até 2 tentativas de correção), timeout, `CancelToken` e retry com backoff.
- Papéis `extractor` e `checker` configuráveis (provedor, modelo, parâmetros). Suporte ao Ollama local. Chaves via `keyring`, com botão "testar conexão".
- **Extrator disparado a cada frase confirmada** (sem intervalo fixo), para detectar a afirmação ~2–5 s depois da fala:
  - cada chamada recebe as **frases novas** mais ~60 s de **contexto anterior** (com os falantes). O prompt só pode extrair afirmações **ancoradas nas frases novas**; o contexto serve apenas para resolver referências ("ele", "isso", "naquele ano"). Assim as janelas não geram duplicatas;
  - **coalescência:** se uma chamada ainda está em andamento quando chegam outras frases, elas são agrupadas na próxima chamada (no máximo 1 chamada em andamento e 1 pendente por sessão), evitando rajadas;
  - **frases incompletas:** se o falante para no meio da ideia, a frase seguinte é reenviada junto com a anterior. O prompt pode responder "aguardar mais contexto" para um trecho que ainda não fecha a afirmação;
  - o extrator devolve só afirmações factuais verificáveis, **normalizadas** (autocontidas) e com a âncora do trecho original.
- Ancoragem: localiza o `source_text` na transcrição (busca aproximada) para obter offsets e timestamps.
- **Dedup:** embeddings locais leves (por exemplo `multilingual-e5-small` via sentence-transformers/ONNX) com limiar, mais confirmação por LLM nos casos limítrofes.
- **Seleção manual:** o trecho selecionado é normalizado e vai para a fila com prioridade.
- Destaques das afirmações na transcrição (estado "na fila").

**Aceite:** num discurso anotado de 10 min, recall ≥ 70% e ≤ 20% de opiniões extraídas (medido em M8, primeira leitura aqui); a afirmação aparece na UI em **≤ 5 s (p90) depois do texto confirmado**, com modelo online; funciona tanto com Ollama local quanto com um modelo online, só trocando a configuração.

### M6 — Checagem · tamanho G
- `SearchProvider` com **SearXNG local** (padrão, Docker), **DuckDuckGo** como reserva automática e **Tavily** opcional; texto das páginas via httpx + trafilatura (ADR 0005).
- **Ranking por tiers:** checadores > oficiais > imprensa > outros, com listas padrão para pt-BR em YAML editável e lista de bloqueio.
- **Pipeline por afirmação** (async, cancelável em cada etapa):
  1. gerar consultas;
  2. buscar;
  3. ranquear e cortar (top N, limite de tokens por fonte);
  4. LLM de veredicto (prompt com data, idioma e afirmação, evidências numeradas, regras de veredicto e definição de "fora de contexto");
  5. **validação de integridade:** URLs ∉ recuperadas são descartadas; < 2 fontes vira "inconclusivo"; JSON inválido é corrigido ou vira erro.
- **Fila:** concorrência configurável (padrão 3), prioridade para pedidos manuais, `check.cancel`, `check.discard`, `check.retry`, eventos de progresso por etapa.
- **UI:** cards com veredicto (ícone, cor e rótulo), confiança, justificativa e fontes (título, domínio, tier, posição, trecho); ligação bidirecional destaque ↔ card; filtros; aviso de IA.

**Aceite:** com uma afirmação real conhecida, veredicto em ≤ 30 s (p90) depois da extração; **de ponta a ponta, da fala ao veredicto na UI, ≤ 35 s (p90)** ao vivo no M2 Pro com modelo online, medido por timestamps registrados em cada etapa (fala, texto confirmado, afirmação, veredicto); cancelar no meio interrompe as requisições em andamento (visível nos logs); um teste automatizado injeta uma URL falsa na resposta do LLM e verifica que ela é removida e o veredicto rebaixado.

### M7 — Exportação e robustez · tamanho P
- Exportação em Markdown (relatório com veredictos, timestamps e fontes), JSON completo, SRT e VTT.
- **Soak test de 2 h** ao vivo, monitorando memória do renderer e do sidecar, tamanho da fila e latência ao longo do tempo.
- Recuperação: sessão interrompida por crash reabre com o áudio e a transcrição até o último ponto, marcada como "interrompida".
- Tratamento de erros dos provedores (rate limit, chave inválida, sem rede) com mensagens claras.
- Logs estruturados com rotação.

**Aceite:** sessão de 2 h sem travar, com crescimento de memória < 20% depois da primeira meia hora; os exports abrem corretamente.

### M8 — Avaliação e ajuste de prompts · tamanho M (pode começar em paralelo com M5)
- **Dataset de veredictos:** cerca de 100 afirmações já checadas por agências brasileiras, com o veredicto mapeado para os 4 rótulos. **Excluir dos resultados de busca o domínio da própria checagem** para não "colar" a resposta, e também medir sem exclusão.
- **Dataset de extração:** 3 a 5 transcrições anotadas manualmente.
- Script `eval/run.py`: matriz de modelos (local × online) e relatório de concordância, matriz de confusão, recall e precisão, latência, e contagem de URLs inválidas (que deve ser zero depois da validação).
- Ciclos de ajuste dos prompts, versionados.

**Aceite:** ≥ 80% de concordância nos veredictos com o melhor modelo online; resultados registrados num ADR.

### M9 — Multiplataforma e empacotamento · tamanho G
- **Windows:** captura de sistema via loopback do Electron, faster-whisper em CPU/CUDA, `keyring` com Credential Manager.
- **Linux:** fallback do monitor de áudio (do spike em M1), Secret Service.
- **Empacotamento:** PyInstaller do sidecar por plataforma (modelos fora do bundle); electron-builder (dmg, nsis, AppImage/deb); ffmpeg LGPL empacotado.
- Builds sem assinatura no CI (assinatura e notarização ficam para a v2).
- Smoke test E2E com Playwright em cada SO: abrir app → transcrever um arquivo de 30 s → gerar uma afirmação → checar com provedores mockados.

**Aceite:** os instaladores das 3 plataformas instalam e passam no smoke test; no Mac, o dmg roda fora do ambiente de desenvolvimento.

## 4. Ordem e paralelismo

```
M0 ─► M1 ─► M2 ─► M3 ─► M4 ──────────────┐
         └──────► M5 ─► M6 ──────────────┼─► M7 ─► M9
                   └──► M8 (contínuo) ───┘
```

- **M5 e M6 dependem só do M0** quanto ao backend: dá para desenvolvê-los com transcrições de texto fixas, em paralelo ao trabalho de áudio. A integração com a UI espera o M3.
- O **M8** começa assim que o M6 tiver o pipeline de checagem rodando pela linha de comando.
- O MVP de uso pessoal no Mac fica pronto ao final do **M7**; o M9 leva o app para as outras plataformas.

## 5. Decisões a registrar como ADR durante a implementação
1. Motor e modelo de STT padrão por plataforma (resultado do benchmark do M2).
2. Taxa de amostragem da gravação Opus (spike do M1).
3. Método de captura do áudio do sistema no Linux.
4. Limiares de clustering da diarização ao vivo e de dedup das afirmações.
5. Prompts v1 de extração e de veredicto (resultado do M8).

## 6. Fora deste plano (roadmap do PRD)
v1.1: URL via yt-dlp, PDF, edição de veredicto, SearXNG/Brave · v2: distribuição assinada, auto-update, "conta rtfc" · v3: overlay, extensão de navegador, colaboração.
