"""Imprime o JSON Schema do protocolo (entrada do gerador de tipos TS).

Uso: `uv run python -m rtfc.protocol.schema`
"""

import json
from typing import Any

from pydantic import TypeAdapter

from rtfc.protocol.messages import PROTOCOL_VERSION, ClientMessage, ServerMessage


def _strip_property_titles(node: Any) -> Any:
    """Remove `title` dos campos; sem isso o gerador TS cria aliases como `Id1`, `Text2`."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for prop in props.values():
                if isinstance(prop, dict):
                    prop.pop("title", None)
        return {k: _strip_property_titles(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_strip_property_titles(v) for v in node]
    return node


def build_schema() -> dict[str, Any]:
    opts: dict[str, Any] = {"ref_template": "#/$defs/{model}", "mode": "serialization"}
    client = _strip_property_titles(TypeAdapter(ClientMessage).json_schema(**opts))
    server = _strip_property_titles(TypeAdapter(ServerMessage).json_schema(**opts))
    defs = {**client.pop("$defs", {}), **server.pop("$defs", {})}
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "RtfcProtocol",
        "description": f"rtfc protocol v{PROTOCOL_VERSION}",
        "type": "object",
        "properties": {
            "client": {"$ref": "#/$defs/ClientMessage"},
            "server": {"$ref": "#/$defs/ServerMessage"},
        },
        "$defs": {
            **defs,
            "ClientMessage": {"oneOf": client["oneOf"]},
            "ServerMessage": {"oneOf": server["oneOf"]},
        },
    }


if __name__ == "__main__":
    print(json.dumps(build_schema(), indent=2, ensure_ascii=False, sort_keys=True))
