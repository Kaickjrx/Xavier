from __future__ import annotations

import json
import random
from pathlib import Path

DEFAULT_PHRASES_PATH = Path("phrases.json")


def load_phrases(path: Path = DEFAULT_PHRASES_PATH) -> list[str]:
    if not path.exists():
        raise FileNotFoundError(
            f"Banco de frases não encontrado em {path}. "
            "Crie o arquivo com uma lista JSON de strings."
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or not all(isinstance(s, str) for s in raw):
        raise ValueError(f"{path} deve ser uma lista JSON de strings.")
    if not raw:
        raise ValueError(f"{path} está vazio.")
    return raw


def pick_phrase(bank: list[str], recent: list[str]) -> str:
    """Escolhe uma frase fora do conjunto recente; cai em qualquer uma se todas estão recentes."""
    candidates = [p for p in bank if p not in recent]
    if not candidates:
        candidates = bank
    return random.choice(candidates)
