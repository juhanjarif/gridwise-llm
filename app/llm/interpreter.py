from __future__ import annotations
import json
import re
from app.llm.prompts import build_messages
from app.llm.providers import AllProvidersFailedError, complete

class InterpretationUnavailableError(Exception):
    """No provider could be reached. Caller must fail safe (e.g. all no_op)."""

class MalformedLLMOutputError(Exception):
    """A provider responded, but the content wasn't parseable JSON."""

def _extract_json_array(raw_text: str) -> list:
    raw_text = raw_text.strip()
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    fenced = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", raw_text, re.DOTALL)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    start, end = raw_text.find("["), raw_text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            parsed = json.loads(raw_text[start : end + 1])
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    raise MalformedLLMOutputError(f"could not extract a JSON array from: {raw_text[:300]}")


async def interpret_notes(
    operator_notes: list[str],
    battery_capacity_kwh: float,
    timeout: float = 20.0,
) -> list[dict]:
    messages = build_messages(operator_notes, battery_capacity_kwh)
    try:
        raw_text = await complete(messages, timeout=timeout)
    except AllProvidersFailedError as exc:
        raise InterpretationUnavailableError(str(exc)) from exc
    return _extract_json_array(raw_text)
