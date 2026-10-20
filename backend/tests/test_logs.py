"""Logs em arquivo (M7): JSON por linha, rotação e sem o token."""

import json
import logging
from pathlib import Path

import pytest

from rtfc import logs
from rtfc.__main__ import _RedactToken


def test_file_log_is_json_rotated_and_redacted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("RTFC_LOGS_DIR", str(tmp_path))
    monkeypatch.setattr(logs, "MAX_BYTES", 2_000)
    path = logs.setup_file_logging(_RedactToken())
    assert path == tmp_path / "backend.log"
    root = logging.getLogger()
    old_level = root.level
    root.setLevel(logging.INFO)
    try:
        log = logging.getLogger("rtfc.teste")
        log.info("conexão em /ws?token=%s", "segredo123")
        try:
            raise ValueError("falhou")
        except ValueError:
            log.exception("erro com %d", 42)
        for i in range(60):
            log.info("linha %d de enchimento para rodar o arquivo", i)
    finally:
        root.setLevel(old_level)
        for h in list(root.handlers):
            if getattr(h, "baseFilename", "").startswith(str(tmp_path)):
                root.removeHandler(h)
                h.close()
    lines = [json.loads(line) for f in sorted(tmp_path.glob("backend.log*")) for line in
             f.read_text().splitlines()]  # fmt: skip
    text = json.dumps(lines)
    assert "segredo123" not in text and "token=***" in text
    assert any(e.get("exc", "").endswith("ValueError: falhou") for e in lines)
    assert {"ts", "level", "logger", "msg"} <= set(lines[0])
    assert (tmp_path / "backend.log.1").exists()  # rodou
