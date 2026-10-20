"""Mapeamento fixo dos selos das agências para os 4 veredictos do rtfc.

Selos ambíguos (que não dizem se a afirmação é verdadeira, como "contraditório", que
compara com falas anteriores) ficam de fora do dataset (None).
"""

import unicodedata

LABEL_MAP: dict[str, str | None] = {
    # Lupa
    "verdadeiro": "verdadeiro",
    "verdadeiro, mas": "fora_de_contexto",
    "verdadeiro mas": "fora_de_contexto",
    "exagerado": "fora_de_contexto",
    "subestimado": "fora_de_contexto",
    "falso": "falso",
    "insustentavel": "inconclusivo",
    "ainda e cedo para dizer": "inconclusivo",
    "contraditorio": None,
    "de olho": None,
    # Aos Fatos
    "impreciso": "fora_de_contexto",
    "distorcido": "fora_de_contexto",
    "nao e bem assim": "fora_de_contexto",
    "sem contexto": "fora_de_contexto",
    # Comprova / AFP / Estadão Verifica
    "comprovado": "verdadeiro",
    "enganoso": "fora_de_contexto",
    "fora de contexto": "fora_de_contexto",
    "enganador": "fora_de_contexto",
    "satira": None,
    "contextualizando": None,
}


def normalize_label(label: str) -> str:
    text = unicodedata.normalize("NFKD", label.strip().lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.replace("…", " ").replace(".", " ").split())


def map_label(label: str) -> str | None:
    return LABEL_MAP.get(normalize_label(label))
