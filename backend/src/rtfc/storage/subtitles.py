"""SRT e WebVTT gravados incrementalmente na pasta da sessão, alinhados com o audio.ogg."""

from pathlib import Path
from typing import TextIO


def _hms(ms: int) -> tuple[int, int, int, int]:
    ms = max(0, ms)
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, milli = divmod(rem, 1000)
    return h, m, s, milli


def srt_time(ms: int) -> str:
    h, m, s, milli = _hms(ms)
    return f"{h:02d}:{m:02d}:{s:02d},{milli:03d}"


def vtt_time(ms: int) -> str:
    h, m, s, milli = _hms(ms)
    return f"{h:02d}:{m:02d}:{s:02d}.{milli:03d}"


class SubtitleWriter:
    """Acrescenta uma legenda por segmento em `transcricao.srt` e `transcricao.vtt`."""

    def __init__(self, session_dir: Path) -> None:
        self.srt_path = session_dir / "transcricao.srt"
        self.vtt_path = session_dir / "transcricao.vtt"
        new_vtt = not self.vtt_path.exists()
        self._srt: TextIO = self.srt_path.open("a", encoding="utf-8", newline="\n")
        self._vtt: TextIO = self.vtt_path.open("a", encoding="utf-8", newline="\n")
        if new_vtt:
            self._vtt.write("WEBVTT\n\n")
            self._vtt.flush()
        self._count = 0

    def add(self, start_ms: int, end_ms: int, text: str, speaker: str | None = None) -> None:
        self._count += 1
        end_ms = max(end_ms, start_ms + 1)
        self._srt.write(f"{self._count}\n{srt_time(start_ms)} --> {srt_time(end_ms)}\n{text}\n\n")
        voice = f"<v {speaker}>" if speaker else ""
        self._vtt.write(f"{vtt_time(start_ms)} --> {vtt_time(end_ms)}\n{voice}{text}\n\n")
        self._srt.flush()
        self._vtt.flush()

    def close(self) -> None:
        self._srt.close()
        self._vtt.close()


def rewrite_subtitles(session_dir: Path, cues: list[tuple[int, int, str, str | None]]) -> None:
    """Regrava SRT e VTT inteiros (depois de renomear ou refinar os falantes).

    `cues`: (início ms, fim ms, texto, nome do falante).
    """
    tmp_dir = session_dir / ".subtitles.tmp"
    tmp_dir.mkdir(exist_ok=True)
    for f in tmp_dir.iterdir():
        f.unlink()
    writer = SubtitleWriter(tmp_dir)
    for start, end, text, speaker in cues:
        writer.add(start, end, text, speaker)
    writer.close()
    writer.srt_path.replace(session_dir / "transcricao.srt")
    writer.vtt_path.replace(session_dir / "transcricao.vtt")
    tmp_dir.rmdir()
