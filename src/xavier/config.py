"""Configurações carregadas de .env / variáveis de ambiente.

Credenciais (e qualquer segredo) NUNCA são logados ou commitados.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def load_env(env_path: Path | None = None) -> None:
    """Carrega .env (se existir) na env atual. Idempotente."""
    if env_path is None:
        env_path = Path(".env")
    if env_path.exists():
        load_dotenv(env_path, override=False)


@dataclass(frozen=True)
class Settings:
    webhook_url: str | None
    ml_email: str | None
    ml_password: str | None

    @property
    def has_ml_credentials(self) -> bool:
        return bool(self.ml_email and self.ml_password)


def get_settings() -> Settings:
    load_env()
    return Settings(
        webhook_url=os.environ.get("XAVIER_WEBHOOK_URL"),
        ml_email=os.environ.get("XAVIER_ML_EMAIL"),
        ml_password=os.environ.get("XAVIER_ML_PASSWORD"),
    )


def redact(value: str | None) -> str:
    """Retorna 'set' / 'unset' — usado em logs para não vazar segredos."""
    return "set" if value else "unset"
