"""Falha se alguma dependência Python de runtime tiver licença GPL/AGPL.

Considera só as dependências de runtime (não o grupo `dev`). LGPL é permitida.
Uso: `uv run python scripts/check_licenses.py`
"""

import json
import re
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
FORBIDDEN = re.compile(r"(^|[^L])A?GPL|General Public License", re.IGNORECASE)
ALLOWED = re.compile(r"LGPL|Lesser General Public License", re.IGNORECASE)


def runtime_packages() -> set[str]:
    out = subprocess.run(
        [
            "uv",
            "export",
            "--no-dev",
            "--all-extras",
            "--no-hashes",
            "--no-emit-project",
            "--format",
            "requirements.txt",
        ],
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    names = set()
    for line in out.splitlines():
        line = line.strip()
        if line and not line.startswith(("#", "-")):
            names.add(re.split(r"[=<>;\[ ]", line, maxsplit=1)[0].lower().replace("_", "-"))
    return names


def main() -> int:
    wanted = runtime_packages()
    raw = subprocess.run(
        ["pip-licenses", "--format=json", "--from=mixed"],
        cwd=BACKEND,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    offenders = []
    seen = set()
    for pkg in json.loads(raw):
        name = pkg["Name"].lower().replace("_", "-")
        if name not in wanted:
            continue
        seen.add(name)
        lic = pkg["License"]
        if FORBIDDEN.search(lic) and not ALLOWED.search(lic):
            offenders.append(f"{pkg['Name']} {pkg['Version']} ({lic})")
    if offenders:
        print(
            "Dependências Python com licença proibida:\n  " + "\n  ".join(offenders),
            file=sys.stderr,
        )
        return 1
    missing = wanted - seen
    if missing:
        print(f"aviso: sem informação de licença para {sorted(missing)}", file=sys.stderr)
    print(f"licenças Python ok ({len(seen)} pacotes de runtime)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
