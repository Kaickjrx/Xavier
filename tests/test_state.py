from datetime import datetime
from pathlib import Path

from xavier.state import (
    CouponSnapshot,
    MonitorState,
    load_state,
    merge_after_run,
    save_state,
)


def test_load_state_returns_empty_when_missing(tmp_path: Path):
    p = tmp_path / "state.json"
    s = load_state(p)
    assert s.active == []
    assert s.announced_codes == []
    assert s.last_run is None


def test_save_load_roundtrip(tmp_path: Path):
    p = tmp_path / "state.json"
    s = MonitorState(
        active=[CouponSnapshot(code="A1", description="Cupom A")],
        announced_codes=["A1", "B2"],
        tested_dead_count=3,
        recent_tested_dead_additions=["X9"],
        recent_phrases=["*OI*"],
        last_run=datetime(2026, 5, 6, 12, 0),
        last_run_result="ok",
    )
    save_state(s, p)
    loaded = load_state(p)
    assert loaded.active == s.active
    assert loaded.announced_codes == s.announced_codes
    assert loaded.tested_dead_count == 3


def test_merge_after_run_extends_history():
    s = MonitorState(
        active=[CouponSnapshot(code="OLD")],
        announced_codes=["OLD"],
        recent_tested_dead_additions=["DEAD1"],
        recent_phrases=["*A*"],
    )
    merged = merge_after_run(
        s,
        current_active=[CouponSnapshot(code="NEW")],
        new_dead=["DEAD2", "DEAD3"],
        used_phrase="*B*",
        result_summary="resumo",
    )
    assert merged.active == [CouponSnapshot(code="NEW")]
    assert "OLD" in merged.announced_codes  # mantém histórico
    assert "NEW" in merged.announced_codes
    assert merged.tested_dead_count == 2
    assert merged.recent_tested_dead_additions == ["DEAD1", "DEAD2", "DEAD3"]
    assert merged.recent_phrases == ["*A*", "*B*"]
    assert merged.last_run is not None


def test_merge_dedupes_announced_codes():
    s = MonitorState(announced_codes=["A1", "B2"])
    merged = merge_after_run(
        s,
        current_active=[CouponSnapshot(code="A1"), CouponSnapshot(code="C3")],
        new_dead=[],
        used_phrase=None,
        result_summary="x",
    )
    # A1 não duplica
    assert merged.announced_codes == ["A1", "B2", "C3"]


def test_merge_caps_phrase_history():
    s = MonitorState(recent_phrases=["1", "2", "3", "4", "5", "6"])
    merged = merge_after_run(
        s,
        current_active=[],
        new_dead=[],
        used_phrase="7",
        result_summary="x",
        max_phrase_history=6,
    )
    assert merged.recent_phrases == ["2", "3", "4", "5", "6", "7"]
