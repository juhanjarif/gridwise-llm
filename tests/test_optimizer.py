from app.schemas import (HourEntry, BatteryConfig, DirectiveInterpretation)
from app.optimizer import build_constraints, solve, replay_and_verify


def _hours():
    return [HourEntry(hour=h, demand_kwh=100, solar_kwh=0, tariff_bdt_per_kwh=5) for h in range(24)]

def _battery():
    return BatteryConfig(
        capacity_kwh=200,
        initial_energy_kwh=100,
        minimum_energy_kwh=20,
        max_charge_kwh_per_hour=50,
        max_discharge_kwh_per_hour=50,
    )

def test_no_directives_produces_valid_plan():
    hours = _hours()
    battery = _battery()
    constraints = build_constraints(hours, battery, [])
    plan = solve(hours, battery, constraints)
    plan, totals = replay_and_verify(hours, battery, plan, constraints)

    assert len(plan) == 24
    assert totals["total_grid_kwh"] > 0
    assert totals["peak_grid_kwh"] <= 200

def test_no_charge_window_forces_zero_charge():
    hours = _hours()
    battery = _battery()
    directive = DirectiveInterpretation(
        note_index=0,
        applies=True,
        directive_type="no_charge_window",
        structured_adjustment={"hours": [0, 1, 2]},
        explanation="Maintenance",
    )
    constraints = build_constraints(hours, battery, [directive])
    plan = solve(hours, battery, constraints)
    plan, _ = replay_and_verify(hours, battery, plan, constraints)

    for entry in plan:
        if entry.hour in {0, 1, 2}:
            assert entry.battery_action != "charge"

def test_end_of_day_neutrality():
    hours = _hours()
    battery = _battery()
    constraints = build_constraints(hours, battery, [])
    plan = solve(hours, battery, constraints)
    assert abs(plan[-1].battery_energy_after_kwh - battery.initial_energy_kwh) < 0.01