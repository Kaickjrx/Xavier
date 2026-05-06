import json
from pathlib import Path

import pytest

from xavier.phrases import load_phrases, pick_phrase


def test_load_phrases_ok(tmp_path: Path):
    p = tmp_path / "phrases.json"
    p.write_text(json.dumps(["*A*", "*B*"]), encoding="utf-8")
    assert load_phrases(p) == ["*A*", "*B*"]


def test_load_phrases_missing_file(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_phrases(tmp_path / "missing.json")


def test_load_phrases_empty_list(tmp_path: Path):
    p = tmp_path / "phrases.json"
    p.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError):
        load_phrases(p)


def test_load_phrases_wrong_type(tmp_path: Path):
    p = tmp_path / "phrases.json"
    p.write_text(json.dumps([1, 2]), encoding="utf-8")
    with pytest.raises(ValueError):
        load_phrases(p)


def test_pick_phrase_avoids_recent():
    bank = ["*A*", "*B*", "*C*"]
    recent = ["*A*", "*B*"]
    for _ in range(20):
        assert pick_phrase(bank, recent) == "*C*"


def test_pick_phrase_falls_back_when_all_recent():
    bank = ["*A*", "*B*"]
    recent = ["*A*", "*B*"]
    chosen = pick_phrase(bank, recent)
    assert chosen in bank
