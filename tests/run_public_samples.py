from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import httpx

from app.optimizer.directives import build_constraints
from app.optimizer.replay import replay_and_verify
from app.schemas import BatteryConfig, DirectiveInterpretation, HourEntry, HourlyPlanEntry

SAMPLES_PATH = Path(__file__).resolve().parent.parent / "data" / "public_samples.json"
TOLERANCE = 0.01


def load_cases() -> list[dict]:
    with SAMPLES_PATH.open(encoding="utf-8") as f:
        return json.load(f)["cases"]


def _ground_truth_directives(case: dict) -> list[DirectiveInterpretation]:
    return [
        DirectiveInterpretation.model_validate(entry)
        for entry in case["expected_output"]["directive_interpretation"]
    ]


def check_interpretation(case: dict, returned: list[dict]) -> list[str]:
    expected = case["expected_output"]["directive_interpretation"]
    errors: list[str] = []
    if len(returned) != len(expected):
        errors.append(f"expected {len(expected)} interpretation entries, got {len(returned)}")
        return errors

    by_index = {e.get("note_index"): e for e in returned}
    for exp in expected:
        idx = exp["note_index"]
        got = by_index.get(idx)
        if got is None:
            errors.append(f"note {idx}: missing from response")
            continue
        if got.get("applies") != exp["applies"]:
            errors.append(f"note {idx}: applies {got.get('applies')} != expected {exp['applies']}")
        if got.get("directive_type") != exp["directive_type"]:
            errors.append(
                f"note {idx}: directive_type {got.get('directive_type')!r} != "
                f"expected {exp['directive_type']!r}"
            )
        if exp["structured_adjustment"] is not None:
            got_adj = got.get("structured_adjustment") or {}
            exp_adj = exp["structured_adjustment"]
            if got_adj.get("hours") != exp_adj.get("hours"):
                errors.append(f"note {idx}: hours {got_adj.get('hours')} != expected {exp_adj.get('hours')}")
            for key, val in exp_adj.items():
                if key == "hours":
                    continue
                got_val = got_adj.get(key)
                if got_val is None or abs(float(got_val) - float(val)) > TOLERANCE:
                    errors.append(f"note {idx}: {key} {got_val} != expected {val}")
    return errors


def check_downstream_application(case: dict, response: dict) -> list[str]:
    hours = [HourEntry.model_validate(h) for h in case["input"]["hours"]]
    battery = BatteryConfig.model_validate(case["input"]["battery"])
    ground_truth = _ground_truth_directives(case)
    constraints = build_constraints(hours, battery, ground_truth)

    try:
        plan = [HourlyPlanEntry.model_validate(p) for p in response["hourly_plan"]]
    except Exception as exc:
        return [f"hourly_plan failed schema validation: {exc}"]

    try:
        _, totals = replay_and_verify(hours, battery, plan, constraints)
    except ValueError as exc:
        return [f"invalid under organizer ground truth: {exc}"]

    expected_cost = case["expected_output"]["total_cost_bdt"]
    team_cost = totals["total_cost_bdt"]
    if team_cost <= TOLERANCE and expected_cost <= TOLERANCE:
        ratio = 1.0
    elif team_cost <= TOLERANCE:
        ratio = 0.0
    else:
        ratio = min(1.0, expected_cost / team_cost)

    errors = []
    if ratio < 0.999:
        errors.append(
            f"cost quality_ratio {ratio:.3f} (team {team_cost:.2f} BDT vs "
            f"organizer optimal {expected_cost:.2f} BDT)"
        )
    return errors


def run(base_url: str) -> bool:
    cases = load_cases()
    all_passed = True

    with httpx.Client(base_url=base_url, timeout=35.0) as client:
        health = client.get("/health")
        if health.status_code != 200 or health.json().get("status") != "ok":
            print(f"FAIL: /health returned {health.status_code} {health.text}")
            return False
        print("PASS: /health OK\n")

        for case in cases:
            case_id = case["id"]
            resp = client.post("/optimize-energy", json=case["input"])
            if resp.status_code != 200:
                print(f"{case_id}: FAIL - HTTP {resp.status_code}: {resp.text[:300]}")
                all_passed = False
                continue

            data = resp.json()
            errors = check_interpretation(
                case, data.get("directive_interpretation", [])
            ) + check_downstream_application(case, data)

            if errors:
                print(f"{case_id}: FAIL")
                for err in errors:
                    print(f"    - {err}")
                all_passed = False
            else:
                print(f"{case_id}: PASS")

    return all_passed


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run all public sample cases against a live GridWise service."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the running service (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    passed = run(args.base_url)
    print("\nALL PASSED" if passed else "\nSOME CASES FAILED")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
