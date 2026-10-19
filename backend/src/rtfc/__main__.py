"""Ponto de entrada do sidecar.

O processo main do Electron inicia este módulo com o token em `RTFC_TOKEN`.
O backend escolhe uma porta livre, imprime uma linha JSON `{"event": "ready",
"port": N, "pid": P}` no stdout e encerra sozinho quando o stdin fecha (ou seja, quando
o processo pai morre), para nunca ficar órfão.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import socket
import sys
import threading

import uvicorn

from rtfc.api import create_app


class _RedactToken(logging.Filter):
    """O uvicorn registra a URL do WebSocket com `?token=…`; o token não pode ir para os logs."""

    _pattern = re.compile(r"token=[^&\s\"']+")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.args:
            record.msg = record.getMessage()
            record.args = None
        record.msg = self._pattern.sub("token=***", str(record.msg))
        return True


def _watch_parent(server: uvicorn.Server, loop: asyncio.AbstractEventLoop) -> None:
    def run() -> None:
        # read() bloqueia até EOF: o pai fechou o pipe ou morreu.
        sys.stdin.buffer.read()
        loop.call_soon_threadsafe(setattr, server, "should_exit", True)

    threading.Thread(target=run, name="parent-watch", daemon=True).start()


async def _serve(port: int, token: str, watch_stdin: bool) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    # listen() antes de anunciar a porta: conexões que chegarem antes do uvicorn
    # começar a aceitar ficam no backlog em vez de serem recusadas.
    sock.listen(128)
    config = uvicorn.Config(create_app(token), log_level="info", access_log=False)
    server = uvicorn.Server(config)
    # Instalado depois do Config, que reconfigura o logging do uvicorn.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).addFilter(_RedactToken())

    if watch_stdin:
        _watch_parent(server, asyncio.get_running_loop())

    actual_port = sock.getsockname()[1]
    # O pid é o do Python (em dev o processo filho direto do Electron é o `uv`).
    print(json.dumps({"event": "ready", "port": actual_port, "pid": os.getpid()}), flush=True)
    await server.serve(sockets=[sock])


def main() -> None:
    parser = argparse.ArgumentParser(prog="rtfc-backend")
    parser.add_argument("--port", type=int, default=0, help="0 = porta livre escolhida pelo SO")
    parser.add_argument(
        "--no-watch-stdin",
        action="store_true",
        help="não encerrar quando o stdin fechar (útil para rodar à mão)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr
    )
    for noisy in ("httpx", "huggingface_hub", "filelock"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    logging.getLogger().addFilter(_RedactToken())

    token = os.environ.get("RTFC_TOKEN")
    if not token:
        print("RTFC_TOKEN não definido", file=sys.stderr)
        sys.exit(2)

    asyncio.run(_serve(args.port, token, watch_stdin=not args.no_watch_stdin))


if __name__ == "__main__":
    main()
