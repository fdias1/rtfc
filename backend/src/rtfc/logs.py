"""Logs estruturados (JSON por linha) com rotação, em `<dados>/logs/backend.log` (M7).

O stderr continua com o formato legível (o Electron repassa para o console em dev). O arquivo
é o que o usuário anexa num relato de problema: nunca leva chaves nem o token.
"""

import json
import logging
import logging.handlers
import os
from datetime import UTC, datetime
from pathlib import Path

MAX_BYTES = 5 * 1024 * 1024
BACKUPS = 5


def logs_dir() -> Path:
    override = os.environ.get("RTFC_LOGS_DIR")
    if override:
        return Path(override)
    from rtfc.sessions.manager import default_sessions_dir

    return default_sessions_dir().parent / "logs"


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        return json.dumps(entry, ensure_ascii=False)


def setup_file_logging(*filters: logging.Filter) -> Path | None:
    """Liga o arquivo de log. Se a pasta não puder ser criada, segue só com o stderr."""
    path = logs_dir() / "backend.log"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
        )
    except OSError:
        logging.getLogger(__name__).warning("não foi possível abrir o log em %s", path)
        return None
    handler.setFormatter(JsonFormatter())
    for f in filters:
        handler.addFilter(f)
    logging.getLogger().addHandler(handler)
    return path
