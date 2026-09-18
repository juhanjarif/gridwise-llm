from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.guardrails.validator import validate_interpretations

SAMPLES_PATH = Path(__file__).resolve().parent.parent / "data" / "public_samples.json"


def _load_cases() -> list[dict]:
    with SAMPLES_PATH.open(encoding="utf-8") as f:
        return json.load(f)["cases"]


CASES = _load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_public_case_directives_pass_through_unchanged(case):
    notes = case["input"]["operator_notes"]
    expected = case["expected_output"]["directive_interpretation"]

    result = validate_interpretations(expected, note_count=len(notes))

    assert len(result) == len(notes)
    for expected_entry, validated in zip(expected, result):
        assert validated.note_index == expected_entry["note_index"]
        assert validated.applies == expected_entry["applies"]
        assert validated.directive_type == expected_entry["directive_type"]
        assert validated.structured_adjustment == expected_entry["structured_adjustment"]


def test_missing_entry_falls_back_to_no_op():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {"hours": [13, 14], "factor": 0.2},
            "explanation": "x",
        }
    ]
    result = validate_interpretations(raw, note_count=2)
    assert result[0].directive_type == "solar_reduction"
    assert result[1].directive_type == "no_op"
    assert result[1].applies is False


def test_duplicate_note_index_keeps_first_and_fallbacks_rest():
    entry = {
        "note_index": 0,
        "applies": True,
        "directive_type": "no_charge_window",
        "structured_adjustment": {"hours": [2, 3]},
        "explanation": "x",
    }
    result = validate_interpretations([entry, entry], note_count=2)
    assert result[0].directive_type == "no_charge_window"
    assert result[1].directive_type == "no_op"


def test_invented_directive_type_falls_back():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "demand_shift",
            "structured_adjustment": {"hours": [1]},
            "explanation": "invented",
        }
    ]
    result = validate_interpretations(raw, note_count=1)
    assert result[0].directive_type == "no_op"
    assert result[0].applies is False


def test_mismatched_structured_adjustment_shape_falls_back():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_discharge_window",
            "structured_adjustment": {"hours": [18, 19], "factor": 0.5},
            "explanation": "wrong shape for this type",
        }
    ]
    result = validate_interpretations(raw, note_count=1)
    assert result[0].directive_type == "no_op"


def test_non_ascending_hours_falls_back():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {"hours": [14, 13]},
            "explanation": "descending",
        }
    ]
    result = validate_interpretations(raw, note_count=1)
    assert result[0].directive_type == "no_op"


def test_out_of_range_note_index_is_dropped():
    raw = [
        {
            "note_index": 5,
            "applies": True,
            "directive_type": "no_charge_window",
            "structured_adjustment": {"hours": [1]},
            "explanation": "out of range",
        }
    ]
    result = validate_interpretations(raw, note_count=2)
    assert all(r.directive_type == "no_op" for r in result)
    assert [r.note_index for r in result] == [0, 1]


def test_non_list_top_level_falls_back_for_every_note():
    result = validate_interpretations("not a list", note_count=3)
    assert len(result) == 3
    assert all(r.directive_type == "no_op" for r in result)


def test_solar_reduction_factor_out_of_range_falls_back():
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "solar_reduction",
            "structured_adjustment": {"hours": [10, 11], "factor": 1.5},
            "explanation": "factor > 1",
        }
    ]
    result = validate_interpretations(raw, note_count=1)
    assert result[0].directive_type == "no_op"


def test_no_op_with_applies_true_falls_back():
    """A no_op MUST have applies=false; if the model contradicts itself,
    guardrails must not silently let a self-inconsistent entry through."""
    raw = [
        {
            "note_index": 0,
            "applies": True,
            "directive_type": "no_op",
            "structured_adjustment": None,
            "explanation": "contradiction",
        }
    ]
    result = validate_interpretations(raw, note_count=1)
    assert result[0].directive_type == "no_op"
    assert result[0].applies is False
