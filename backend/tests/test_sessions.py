"""Sessões ponta a ponta pelo WebSocket (precisam de ffmpeg/ffprobe no PATH)."""

import json
import math
import shutil
import struct
import subprocess
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.testclient import WebSocketTestSession

from rtfc.api import create_app
from rtfc.sessions import SessionManager

pytestmark = pytest.mark.skipif(
    not (shutil.which("ffmpeg") and shutil.which("ffprobe")), reason="ffmpeg não instalado"
)

TOKEN = "t"


def sine_pcm(seconds: float, rate: int = 48_000, freq: float = 440.0) -> bytes:
    n = int(seconds * rate)
    return struct.pack(
        f"<{n}h", *(int(12000 * math.sin(2 * math.pi * freq * i / rate)) for i in range(n))
    )


def media_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return float(out.stdout.strip())


def recv_until(ws: WebSocketTestSession, type_: str) -> dict[str, Any]:
    while True:
        msg: dict[str, Any] = json.loads(ws.receive_text())
        if msg["type"] == type_:
            return msg
        if msg["type"] == "error":
            raise AssertionError(msg)


@pytest.fixture
def manager(tmp_path: Path) -> SessionManager:
    return SessionManager(tmp_path / "sessions")


@pytest.fixture
def client(manager: SessionManager) -> TestClient:
    return TestClient(create_app(TOKEN, sessions=manager))


def test_live_session_records_ogg_and_feeds_pipeline(
    client: TestClient, manager: SessionManager
) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        recv_until(ws, "hello")
        ws.send_text(json.dumps({"type": "session.start", "id": "1", "source": "mic"}))
        started = recv_until(ws, "session.started")["session"]
        assert started["status"] == "recording"
        session = manager.get(started["id"])

        pcm = sine_pcm(2.5)
        for i in range(0, len(pcm), 9600):  # blocos de 100 ms
            ws.send_bytes(pcm[i : i + 9600])

        ws.send_text(json.dumps({"type": "session.stop", "id": "2", "session_id": started["id"]}))
        ended = recv_until(ws, "session.ended")

    assert ended["id"] == "2"
    assert ended["reason"] == "stopped"
    assert ended["session"]["duration_ms"] == 2500
    ogg = Path(started["audio_path"])
    assert ogg.name == "audio.ogg"
    assert media_duration(ogg) == pytest.approx(2.5, abs=0.1)
    # 16 kHz no pipeline (±1 bloco de reamostragem).
    assert session.buffer.duration_ms == pytest.approx(2500, abs=50)
    saved = json.loads((Path(started["dir"]) / "session.json").read_text())
    assert saved["status"] == "completed"
    assert saved["ended_at"]


def test_disconnect_finalizes_live_recording(client: TestClient) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        recv_until(ws, "hello")
        ws.send_text(json.dumps({"type": "session.start", "id": "1", "source": "system"}))
        started = recv_until(ws, "session.started")["session"]
        ws.send_bytes(sine_pcm(1.0))
        ws.send_text(json.dumps({"type": "ping", "id": "p"}))
        recv_until(ws, "pong")
    # Ao fechar a conexão a sessão é encerrada e o ogg fica válido.
    assert media_duration(Path(started["audio_path"])) == pytest.approx(1.0, abs=0.1)
    saved = json.loads((Path(started["dir"]) / "session.json").read_text())
    assert saved["status"] == "completed"


def test_file_session_decodes_with_progress(client: TestClient, tmp_path: Path) -> None:
    wav = tmp_path / "fala.wav"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "sine=duration=3", str(wav)], check=True
    )
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        recv_until(ws, "hello")
        ws.send_text(
            json.dumps(
                {"type": "session.start", "id": "1", "source": "file", "file_path": str(wav)}
            )
        )
        started = recv_until(ws, "session.started")["session"]
        assert started["status"] == "processing"
        assert started["media_kind"] == "audio"
        assert started["audio_path"] == str(wav)
        progress = recv_until(ws, "session.progress")
        assert progress["total_ms"] == 3000
        ended = recv_until(ws, "session.ended")
    assert ended["reason"] == "completed"
    assert ended["session"]["duration_ms"] == 3000


def test_file_session_detects_video(client: TestClient, tmp_path: Path) -> None:
    mp4 = tmp_path / "video.mp4"
    subprocess.run(
        [
            "ffmpeg", "-v", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=64x64:d=1",
            "-f", "lavfi", "-i", "sine=duration=1",
            "-shortest", "-pix_fmt", "yuv420p", str(mp4),
        ],
        check=True,
    )  # fmt: skip
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        recv_until(ws, "hello")
        ws.send_text(
            json.dumps(
                {"type": "session.start", "id": "1", "source": "file", "file_path": str(mp4)}
            )
        )
        assert recv_until(ws, "session.started")["session"]["media_kind"] == "video"
        assert recv_until(ws, "session.ended")["reason"] == "completed"


def test_invalid_file_is_rejected(client: TestClient, tmp_path: Path) -> None:
    bogus = tmp_path / "nao-e-midia.mp3"
    bogus.write_text("isto não é áudio")
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        recv_until(ws, "hello")
        ws.send_text(
            json.dumps(
                {"type": "session.start", "id": "1", "source": "file", "file_path": str(bogus)}
            )
        )
        reply = json.loads(ws.receive_text())
    assert reply["type"] == "error"
    assert reply["id"] == "1"
    assert reply["code"] == "session_error"


def test_audio_without_session_warns_once(client: TestClient) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        recv_until(ws, "hello")
        ws.send_bytes(b"\x00\x00" * 100)
        ws.send_bytes(b"\x00\x00" * 100)
        ws.send_text(json.dumps({"type": "ping", "id": "p"}))
        first = json.loads(ws.receive_text())
        second = json.loads(ws.receive_text())
    assert first["code"] == "no_live_session"
    assert second["type"] == "pong"


def test_list_rename_delete_sessions(client: TestClient, manager: SessionManager) -> None:
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        recv_until(ws, "hello")
        ws.send_text(json.dumps({"type": "session.start", "id": "1", "source": "mic"}))
        sid = recv_until(ws, "session.started")["session"]["id"]
        ws.send_bytes(sine_pcm(0.5))
        ws.send_text(json.dumps({"type": "session.stop", "id": "2", "session_id": sid}))
        recv_until(ws, "session.ended")

        ws.send_text(json.dumps({"type": "session.list", "id": "3"}))
        items = recv_until(ws, "session.list.result")["sessions"]
        assert [i["session"]["id"] for i in items] == [sid]
        assert items[0]["size_bytes"] > 0

        ws.send_text(
            json.dumps(
                {"type": "session.rename", "id": "4", "session_id": sid, "title": " Debate "}
            )
        )
        assert recv_until(ws, "session.updated")["session"]["title"] == "Debate"

        ws.send_text(json.dumps({"type": "session.delete", "id": "5", "session_id": sid}))
        assert recv_until(ws, "session.deleted")["session_id"] == sid
        assert not (manager.sessions_dir / sid).exists()

        ws.send_text(json.dumps({"type": "session.delete", "id": "6", "session_id": "../etc"}))
        reply = json.loads(ws.receive_text())
        assert reply["type"] == "error" and reply["code"] == "session_error"


def test_list_marks_abandoned_sessions_as_interrupted(manager: SessionManager) -> None:
    import asyncio

    from rtfc.protocol import SessionInfo

    sid = "20260101-120000-mic-abcd"
    d = manager.sessions_dir / sid
    d.mkdir(parents=True)
    info = SessionInfo(
        id=sid, source="mic", status="recording", dir=str(d),
        audio_path=str(d / "audio.ogg"), started_at="2026-01-01T15:00:00+00:00",
    )  # fmt: skip
    (d / "session.json").write_text(info.model_dump_json())
    items = asyncio.run(manager.list_sessions())
    assert items[0].session.status == "interrupted"
    assert '"interrupted"' in (d / "session.json").read_text()


def test_can_start_another_live_session_after_stopping(client: TestClient) -> None:
    """Regressão: depois de encerrar pelo botão, a 2ª sessão ao vivo era recusada."""
    with client.websocket_connect(f"/ws?token={TOKEN}") as ws:
        recv_until(ws, "hello")
        for i, source in enumerate(["system", "system", "mic"]):
            ws.send_text(json.dumps({"type": "session.start", "id": f"s{i}", "source": source}))
            sid = recv_until(ws, "session.started")["session"]["id"]
            ws.send_bytes(sine_pcm(0.3))
            ws.send_text(json.dumps({"type": "session.stop", "id": f"e{i}", "session_id": sid}))
            assert recv_until(ws, "session.ended")["reason"] == "stopped"
