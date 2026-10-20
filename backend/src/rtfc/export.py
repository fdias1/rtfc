"""Exportação de uma sessão (M7): relatório em Markdown, JSON completo, SRT e VTT."""

from datetime import UTC, datetime
from typing import Any, Literal

from rtfc import __version__
from rtfc.claims.pipeline import to_check_data
from rtfc.diarization.clustering import speaker_label
from rtfc.protocol import ClaimData, SessionInfo, TranscriptSegmentData
from rtfc.storage import CheckStore, render_srt, render_vtt

Format = Literal["md", "json", "srt", "vtt"]

VERDICT_LABEL = {
    "verdadeiro": "Verdadeiro",
    "fora_de_contexto": "Fora de contexto",
    "falso": "Falso",
    "inconclusivo": "Inconclusivo",
}
VERDICT_ORDER = ["falso", "fora_de_contexto", "verdadeiro", "inconclusivo"]
TIER_LABEL = {
    "primary": "fonte primária",
    "official": "fonte oficial",
    "factchecker": "checagem",
    "press": "imprensa",
    "other": "outra",
}
SOURCE_LABEL = {"mic": "Microfone", "system": "Áudio do sistema", "file": "Arquivo"}


def _clock(ms: int) -> str:
    s = ms // 1000
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def title(info: SessionInfo) -> str:
    if info.title:
        return info.title
    if info.source == "file" and info.file_path:
        return info.file_path.replace("\\", "/").rsplit("/", 1)[-1]
    return SOURCE_LABEL[info.source]


def filename(info: SessionInfo, fmt: Format) -> str:
    base = "".join(c if c.isalnum() or c in " -_." else "_" for c in title(info)).strip()
    stamp = info.started_at[:10]
    return f"rtfc {stamp} {base}.{fmt}" if base else f"rtfc {stamp}.{fmt}"


def _cues(info: SessionInfo, segments: list[TranscriptSegmentData]) -> list[Any]:
    return [
        (s.start_ms, s.end_ms, s.text, speaker_label(s.speaker, info.speakers)) for s in segments
    ]


def _md_escape(text: str) -> str:
    return text.replace("\n", " ").strip()


def markdown(
    info: SessionInfo, segments: list[TranscriptSegmentData], claims: list[ClaimData]
) -> str:
    names = info.speakers
    shown = [c for c in claims if c.status != "discarded" and not c.dedup_of]
    checked = [c for c in shown if c.check]
    when = datetime.fromisoformat(info.started_at).astimezone()
    lines = [f"# {title(info)}", ""]
    meta = [
        f"- **Data:** {when.strftime('%d/%m/%Y %H:%M')}",
        f"- **Fonte:** {SOURCE_LABEL[info.source]}"
        + (f" ({info.file_path})" if info.source == "file" and info.file_path else ""),
    ]
    if info.duration_ms:
        meta.append(f"- **Duração:** {_clock(info.duration_ms)}")
    if info.status == "interrupted":
        meta.append(
            "- **Atenção:** sessão interrompida; a transcrição vai até o último ponto salvo"
        )
    lines += [*meta, ""]
    if info.context:
        lines += ["## Contexto", "", _md_escape(info.context), ""]
    speakers = sorted({s.speaker for s in segments if s.speaker}, key=lambda x: (len(x), x))
    if speakers:
        lines += ["## Falantes", ""]
        lines += [f"- {speaker_label(s, names)}" for s in speakers]
        lines.append("")

    lines += ["## Resumo", ""]
    counts = {v: sum(1 for c in checked if c.check and c.check.verdict == v) for v in VERDICT_ORDER}
    lines.append(f"{len(shown)} afirmações; {len(checked)} checadas.")
    lines.append("")
    lines += [f"- {VERDICT_LABEL[v]}: {n}" for v, n in counts.items() if n]
    pending = len(shown) - len(checked)
    if pending:
        lines.append(f"- Sem resultado (pendentes, canceladas ou com erro): {pending}")
    lines.append("")

    if shown:
        lines += ["## Afirmações", ""]
        for c in sorted(shown, key=lambda c: c.start_ms):
            who = speaker_label(c.speaker, names)
            head = f"### [{_clock(c.start_ms)}]" + (f" {who}" if who else "")
            lines += [head, "", f"> {_md_escape(c.source_text or c.text)}", ""]
            if c.text and c.text != c.source_text:
                lines += [f"**Afirmação checada:** {_md_escape(c.text)}", ""]
            if not c.check:
                state = {
                    "error": "erro na checagem",
                    "cancelled": "cancelada",
                    "queued": "checagem em andamento",
                    "checking": "checagem em andamento",
                }.get(c.status, "não checada")
                lines += [f"**Veredicto:** — ({state})", ""]
                continue
            k = c.check
            how = f"revisado com {k.model}" if c.reviewed else f"checado com {k.model}"
            pct = round(k.confidence * 100)
            lines.append(f"**Veredicto: {VERDICT_LABEL[k.verdict]}** · confiança {pct}% · {how}")
            if c.previous_verdict and c.previous_verdict != k.verdict:
                lines.append(f"(na checagem ao vivo: {VERDICT_LABEL[c.previous_verdict]})")
            lines += ["", _md_escape(k.justification), ""]
            if k.sources:
                lines.append("**Fontes:**")
                lines.append("")
                for src in k.sources:
                    quote = f' — "{_md_escape(src.quote)}"' if src.quote else ""
                    lines.append(
                        f"- [{_md_escape(src.title) or src.domain}]({src.url}) · {src.domain}"
                        f" · {TIER_LABEL.get(src.tier, src.tier)} · {src.stance}{quote}"
                    )
                lines.append("")

    lines += ["## Transcrição", ""]
    prev: str | None = "∅"
    for s in segments:
        who = speaker_label(s.speaker, names)
        if who != prev and who:
            lines.append(f"**[{_clock(s.start_ms)}] {who}:** {s.text}")
        else:
            lines.append(f"[{_clock(s.start_ms)}] {s.text}")
        lines.append("")
        prev = who
    lines += [
        "---",
        "",
        f"Gerado pelo rtfc {__version__} em "
        f"{datetime.now().astimezone().strftime('%d/%m/%Y %H:%M')}. "
        "Veredictos gerados por IA: confira sempre as fontes.",
        "",
    ]
    return "\n".join(lines)


def to_json(
    info: SessionInfo,
    segments: list[TranscriptSegmentData],
    claims: list[ClaimData],
    checks: CheckStore | None,
) -> dict[str, Any]:
    def history(claim_id: str) -> dict[str, Any]:
        out: dict[str, Any] = {}
        if checks:
            for p in ("live", "review"):
                c = checks.get(claim_id, p)
                if c:
                    out[p] = to_check_data(c).model_dump()
        return out

    return {
        "format": "rtfc-session",
        "version": 1,
        "exported_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "rtfc_version": __version__,
        "session": info.model_dump(),
        "speakers": {
            s: speaker_label(s, info.speakers)
            for s in sorted({x.speaker for x in segments if x.speaker})
        },
        "segments": [s.model_dump() for s in segments],
        "claims": [c.model_dump() | {"checks": history(c.id)} for c in claims],
    }


def render(
    fmt: Format,
    info: SessionInfo,
    segments: list[TranscriptSegmentData],
    claims: list[ClaimData],
    checks: CheckStore | None = None,
) -> str:
    import json

    if fmt == "md":
        return markdown(info, segments, claims)
    if fmt == "json":
        return json.dumps(to_json(info, segments, claims, checks), ensure_ascii=False, indent=1)
    cues = _cues(info, segments)
    return render_srt(cues) if fmt == "srt" else render_vtt(cues)
