"""Monta o dataset de avaliação de veredictos a partir de checagens publicadas.

Lê os RSS de agências brasileiras (e URLs extras), extrai de cada artigo as afirmações
checadas e o selo da agência com um LLM, e mapeia o selo para os 4 veredictos do rtfc
por uma tabela fixa (labels.py). Do artigo, guarda só a afirmação curta, o falante, o selo,
a data e a URL — nunca o texto da checagem.

Uso (da raiz):
    uv run --project backend python eval/verdicts/build_dataset.py [--max-articles 12] [urls...]
Saída: eval/verdicts/dataset.jsonl (revise à mão antes de usar como referência).
"""

import argparse
import asyncio
import hashlib
import json
import re
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from labels import map_label, normalize_label  # noqa: E402

from rtfc.config import KeyringSecretStore, LlmRole  # noqa: E402
from rtfc.llm import LlmClient  # noqa: E402
from rtfc.search.fetch import USER_AGENT  # noqa: E402

HERE = Path(__file__).resolve().parent
FEEDS = (
    "https://lupa.uol.com.br/feed",
    "https://www.aosfatos.org/noticias/feed/",
    "https://projetocomprova.com.br/feed/",
)

PROMPT = """Você lê um artigo de checagem de fatos publicado por uma agência e lista cada afirmação checada.
Para cada uma:
- `claim`: a afirmação checada, como foi dita (curta, até 40 palavras);
- `speaker`: quem disse ou quem espalhou (nome e partido/cargo, ou "post nas redes");
- `label`: o selo EXATO dado pela agência (ex.: FALSO, VERDADEIRO, EXAGERADO, SUBESTIMADO, CONTRADITÓRIO, INSUSTENTÁVEL, IMPRECISO, DISTORCIDO, ENGANOSO, COMPROVADO, AINDA É CEDO PARA DIZER, VERDADEIRO, MAS);
- `said_on`: data em que foi dita (AAAA-MM-DD) se o artigo indicar; senão a data do artigo.
Use SOMENTE selos que aparecem escritos no artigo para aquela afirmação. Se o texto não for uma
checagem com selos explícitos (reportagem, análise, observatório, lista de casos), devolva
`items` vazio. Ignore trechos que não sejam afirmações checadas com selo. Responda só com o JSON."""

# Só seções de checagem; reportagens e análises das agências não têm selos por afirmação.
CHECK_PATH = re.compile(r"/(checagem|verificacao|jornalismo/\d{4}/\d{2}/\d{2}/e-(falso|falsa|verdade))|aosfatos\.org/noticias/|projetocomprova\.com\.br/publica")


class Item(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claim: str
    speaker: str
    label: str
    said_on: str


class Items(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[Item]


BLOCK_TAGS = {"p", "div", "li", "h1", "h2", "h3", "h4", "blockquote", "br", "tr", "figcaption"}


async def page_text(http: httpx.AsyncClient, url: str) -> str | None:
    """Texto do artigo preservando os selos.

    O extrator usado pelo app (trafilatura) descarta os blocos visuais onde as agências põem
    os selos (ex.: <div class="block-text"><strong>FALSO</strong>), então aqui o HTML é
    convertido em texto bloco a bloco, sem filtro de "layout".
    """
    from lxml import html as lhtml

    try:
        r = await http.get(url)
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    root = lhtml.fromstring(r.text)
    for bad in root.xpath("//script|//style|//noscript|//nav|//header|//footer|//aside|//form"):
        bad.drop_tree()
    main = (root.xpath("//article") or root.xpath("//main") or [root])[0]
    parts: list[str] = []
    for el in main.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag in BLOCK_TAGS:
            parts.append("\n")
        if el.text:
            parts.append(el.text)
        if el.tail:
            parts.append(el.tail)
    text = re.sub(r"\n\s*\n+", "\n\n", "".join(parts))
    return re.sub(r"[ \t]+", " ", text).strip() or None


async def feed_links(http: httpx.AsyncClient, url: str) -> list[str]:
    try:
        r = await http.get(url)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"feed indisponível: {url} ({exc})", file=sys.stderr)
        return []
    items = re.findall(r"<item>.*?</item>", r.text, re.S)
    return [m.group(1).strip() for i in items if (m := re.search(r"<link>([^<]+)</link>", i))]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*", help="artigos extras de checagem")
    ap.add_argument("--max-articles", type=int, default=12)
    ap.add_argument("--model", default="openai:gpt-5.4-mini")
    args = ap.parse_args()

    http = httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    links = list(args.urls)
    for feed in FEEDS:
        links += await feed_links(http, feed)
    # Artigos de checagem (não a home nem páginas de categoria), sem repetir.
    seen: set[str] = set()
    articles = [
        u for u in links if CHECK_PATH.search(u) and not (u in seen or seen.add(u))
    ][: args.max_articles]

    provider, model = args.model.split(":", 1)
    client = LlmClient(LlmRole(provider=provider, model=model), KeyringSecretStore(), timeout_s=120)
    out_path = HERE / "dataset.jsonl"
    existing = {json.loads(line)["id"] for line in out_path.open(encoding="utf-8")} if out_path.exists() else set()
    added = skipped = unlabeled = 0
    with out_path.open("a", encoding="utf-8") as out:
        for url in articles:
            text = await page_text(http, url)
            if not text:
                print(f"sem texto: {url}", file=sys.stderr)
                continue
            result = await client.structured(
                [{"role": "system", "content": PROMPT}, {"role": "user", "content": text[:30000]}], Items
            )
            plain = normalize_label(text)
            for it in result.value.items:
                expected = map_label(it.label)
                if expected is None:
                    skipped += 1
                    continue
                # O selo precisa estar escrito no artigo (o LLM não pode "deduzir" um selo).
                if normalize_label(it.label) not in plain:
                    unlabeled += 1
                    continue
                cid = hashlib.sha1(f"{url}|{it.claim}".encode()).hexdigest()[:10]
                if cid in existing:
                    continue
                existing.add(cid)
                row = {
                    "id": cid,
                    "claim": it.claim.strip(),
                    "speaker": it.speaker.strip(),
                    "said_on": it.said_on,
                    "label_original": it.label.strip(),
                    "expected": expected,
                    "source_url": url,
                }
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
                added += 1
            print(f"{url}: {len(result.value.items)} afirmações", file=sys.stderr)
    await http.aclose()
    print(
        f"adicionadas {added}, ignoradas: selo ambíguo {skipped}, selo ausente do artigo "
        f"{unlabeled}; total {len(existing)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
