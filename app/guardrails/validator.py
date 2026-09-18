from __future__ import annotations

from pydantic import ValidationError

from app.schemas import ALLOWED_DIRECTIVE_TYPES, DirectiveInterpretation


def _fallback_no_op(note_index: int, reason: str) -> DirectiveInterpretation:
    return DirectiveInterpretation(
        note_index=note_index,
        applies=False,
        directive_type="no_op",
        structured_adjustment=None,
        explanation=f"Guardrail fallback: {reason}",
    )


def validate_interpretations(
    raw_entries: list,
    note_count: int,
) -> list[DirectiveInterpretation]:
    by_index: dict[int, DirectiveInterpretation] = {}

    for raw in raw_entries if isinstance(raw_entries, list) else []:
        if not isinstance(raw, dict):
            continue

        note_index = raw.get("note_index")
        # Some LLMs emit JSON integers as floats (e.g. 0.0 instead of 0);
        # coerce integral floats before the int check so a valid directive
        # doesn't get silently dropped to no_op over a formatting quirk.
        # bool is excluded explicitly since bool is an int subclass in
        # Python (isinstance(True, int) is True) and would otherwise slip
        # through as note_index 0 or 1.
        if isinstance(note_index, float) and note_index.is_integer():
            note_index = int(note_index)
        if (
            not isinstance(note_index, int)
            or isinstance(note_index, bool)
            or not (0 <= note_index < note_count)
        ):
            continue
        if note_index in by_index:
            continue

        directive_type = raw.get("directive_type")
        if directive_type not in ALLOWED_DIRECTIVE_TYPES:
            by_index[note_index] = _fallback_no_op(
                note_index, f"unsupported directive_type {directive_type!r}"
            )
            continue

        try:
            validated = DirectiveInterpretation.model_validate(raw)
        except ValidationError as exc:
            by_index[note_index] = _fallback_no_op(
                note_index, f"schema validation failed: {exc.errors()[0]['msg']}"
            )
            continue

        by_index[note_index] = validated

    return [
        by_index.get(i) or _fallback_no_op(i, "missing from LLM output")
        for i in range(note_count)
    ]
