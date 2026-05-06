from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

DEFAULT_STATE_PATH = Path("state/ml-cupons-state.json")


class CouponSnapshot(BaseModel):
    """Cupom ativo atualmente em /cupons/active do ML."""
    code: str
    description: Optional[str] = None


class MonitorState(BaseModel):
    active: list[CouponSnapshot] = Field(default_factory=list)
    announced_codes: list[str] = Field(default_factory=list)
    tested_dead_count: int = 0
    recent_tested_dead_additions: list[str] = Field(default_factory=list)
    recent_phrases: list[str] = Field(
        default_factory=list,
        description="Últimas frases de abertura usadas no webhook 3 (para evitar repetição).",
    )
    last_run: Optional[datetime] = None
    last_run_result: Optional[str] = None

    @property
    def active_codes(self) -> set[str]:
        return {c.code for c in self.active}

    @property
    def announced_set(self) -> set[str]:
        return set(self.announced_codes)

    @property
    def recent_dead_set(self) -> set[str]:
        return set(self.recent_tested_dead_additions)


def load_state(path: Path = DEFAULT_STATE_PATH) -> MonitorState:
    if not path.exists():
        return MonitorState()
    raw = json.loads(path.read_text(encoding="utf-8"))
    return MonitorState.model_validate(raw)


def save_state(state: MonitorState, path: Path = DEFAULT_STATE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def merge_after_run(
    state: MonitorState,
    *,
    current_active: list[CouponSnapshot],
    new_dead: list[str],
    used_phrase: Optional[str],
    result_summary: str,
    max_dead_history: int = 30,
    max_phrase_history: int = 6,
) -> MonitorState:
    """Aplica as regras de atualização de estado pós-execução."""
    active_codes = [c.code for c in current_active]
    announced = list(dict.fromkeys(state.announced_codes + active_codes))

    dead_history = list(dict.fromkeys(state.recent_tested_dead_additions + new_dead))
    if len(dead_history) > max_dead_history:
        dead_history = dead_history[-max_dead_history:]

    phrase_history = list(state.recent_phrases)
    if used_phrase:
        phrase_history.append(used_phrase)
        if len(phrase_history) > max_phrase_history:
            phrase_history = phrase_history[-max_phrase_history:]

    return state.model_copy(
        update={
            "active": current_active,
            "announced_codes": announced,
            "tested_dead_count": state.tested_dead_count + len(new_dead),
            "recent_tested_dead_additions": dead_history,
            "recent_phrases": phrase_history,
            "last_run": datetime.utcnow(),
            "last_run_result": result_summary,
        }
    )
