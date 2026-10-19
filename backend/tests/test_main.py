"""Testa o processo do sidecar de ponta a ponta: anuncia a porta e morre com o pai."""

import json
import os
import subprocess
import sys
import urllib.request


def test_sidecar_announces_port_and_exits_on_stdin_close() -> None:
    env = {**os.environ, "RTFC_TOKEN": "t"}
    proc = subprocess.Popen(
        [sys.executable, "-m", "rtfc"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        env=env,
    )
    try:
        assert proc.stdout is not None and proc.stdin is not None
        ready = json.loads(proc.stdout.readline())
        assert ready["event"] == "ready"
        req = urllib.request.Request(
            f"http://127.0.0.1:{ready['port']}/health", headers={"Authorization": "Bearer t"}
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            assert json.loads(resp.read())["status"] == "ok"

        proc.stdin.close()
        assert proc.wait(timeout=10) == 0
    finally:
        proc.kill()


def test_sidecar_requires_token() -> None:
    env = {k: v for k, v in os.environ.items() if k != "RTFC_TOKEN"}
    result = subprocess.run(
        [sys.executable, "-m", "rtfc"], env=env, capture_output=True, timeout=10
    )
    assert result.returncode == 2


def test_redact_token_filter() -> None:
    import logging

    from rtfc.__main__ import _RedactToken

    record = logging.LogRecord(
        "uvicorn.error",
        logging.INFO,
        __file__,
        1,
        '%s - "WebSocket %s" [accepted]',
        ("127.0.0.1:1", "/ws?token=abc123&x=1"),
        None,
    )
    assert _RedactToken().filter(record)
    assert record.getMessage() == '127.0.0.1:1 - "WebSocket /ws?token=***&x=1" [accepted]'
