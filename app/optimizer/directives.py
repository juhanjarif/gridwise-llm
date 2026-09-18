from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas import (
    DirectiveInterpretation,
    HourEntry,
    BatteryConfig,
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeWindowAdjustment,
    NoDischargeWindowAdjustment,
    MaxGridWindowAdjustment,
)

@dataclass
class EffectiveConstraints:
    effective_solar_kwh: list[float]

    min_battery_energy_kwh: list[float]

    no_charge_hours: set[int] = field(default_factory=set)
    no_discharge_hours: set[int] = field(default_factory=set)
    max_grid_kwh_per_hour: list[float | None] = field(default_factory=list)

def build_constraints(hours: list[HourEntry], battery: BatteryConfig, directives: list[DirectiveInterpretation]) -> EffectiveConstraints:
    n = 24
    by_hour = {h.hour: h for h in hours}

    effective_solar = [float(by_hour[h].solar_kwh) for h in range(n)]
    min_battery = [float(battery.minimum_energy_kwh) for _ in range(n)]
    no_charge: set[int] = set()
    no_discharge: set[int] = set()
    max_grid: list[float | None] = [None] * n

    for d in directives:
        if d.directive_type == "no_op":
            continue

        adj = d.adjustment_as_model()
        if isinstance(adj, SolarReductionAdjustment):
            for h in adj.hours:
                effective_solar[h] *= float(adj.factor)

        elif isinstance(adj, MinimumBatteryReserveAdjustment):
            # Clamp to capacity: schemas.py only enforces >= 0 on this
            # value, not <= capacity, so an LLM-provided reserve above the
            # battery's actual capacity (e.g. a bad percentage conversion)
            # would otherwise hand the solver an infeasible lowBound >
            # upBound and crash it (see the PulpSolverError handling in
            # main.py).
            cap_val = float(battery.capacity_kwh)
            for h in adj.hours:
                clamped = min(float(adj.minimum_energy_kwh), cap_val)
                if clamped > min_battery[h]:
                    min_battery[h] = clamped

        elif isinstance(adj, NoChargeWindowAdjustment):
            no_charge.update(adj.hours)

        elif isinstance(adj, NoDischargeWindowAdjustment):
            no_discharge.update(adj.hours)

        elif isinstance(adj, MaxGridWindowAdjustment):
            for h in adj.hours:
                cap = float(adj.max_grid_kwh)
                if max_grid[h] is None or cap < max_grid[h]:
                    max_grid[h] = cap

        else:
            raise ValueError(f"Unhandled directive type: {d.directive_type}")

    return EffectiveConstraints(
        effective_solar_kwh=effective_solar,
        min_battery_energy_kwh=min_battery,
        no_charge_hours=no_charge,
        no_discharge_hours=no_discharge,
        max_grid_kwh_per_hour=max_grid,
    )