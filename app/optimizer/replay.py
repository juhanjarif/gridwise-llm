from __future__ import annotations
from app.schemas import HourEntry, BatteryConfig, HourlyPlanEntry
from app.optimizer.directives import EffectiveConstraints

TOL = 0.01

def replay_and_verify(hours: list[HourEntry], battery: BatteryConfig, plan: list[HourlyPlanEntry], constraints: EffectiveConstraints) -> tuple[list[HourlyPlanEntry], dict[str, float]]:
    by_hour = {h.hour: h for h in hours}

    if len(plan) != 24 or sorted(p.hour for p in plan) != list(range(24)):
        raise ValueError("hourly_plan must contain exactly hours 0..23")

    ordered = sorted(plan, key=lambda p: p.hour)

    cap = float(battery.capacity_kwh)
    max_chg = float(battery.max_charge_kwh_per_hour)
    max_dis = float(battery.max_discharge_kwh_per_hour)
    init_e = float(battery.initial_energy_kwh)

    prev_energy = init_e
    total_grid = 0.0
    total_cost = 0.0
    peak_grid = 0.0

    for entry in ordered:
        h = entry.hour
        src = by_hour[h]

        if entry.grid_kwh < -TOL or entry.solar_used_kwh < -TOL or entry.battery_kwh < -TOL:
            raise ValueError(f"Hour {h}: negative value in plan entry")

        solar_limit = constraints.effective_solar_kwh[h] + TOL
        if entry.solar_used_kwh > solar_limit:
            raise ValueError(
                f"Hour {h}: solar_used_kwh {entry.solar_used_kwh} exceeds effective "
                f"solar {constraints.effective_solar_kwh[h]}"
            )

        if entry.battery_action == "idle" and entry.battery_kwh > TOL:
            raise ValueError(f"Hour {h}: idle action has nonzero battery_kwh")
        if entry.battery_action == "charge" and entry.battery_kwh > max_chg + TOL:
            raise ValueError(f"Hour {h}: charge exceeds max_charge_kwh_per_hour")
        if entry.battery_action == "discharge" and entry.battery_kwh > max_dis + TOL:
            raise ValueError(f"Hour {h}: discharge exceeds max_discharge_kwh_per_hour")

        if h in constraints.no_charge_hours and entry.battery_action == "charge" and entry.battery_kwh > TOL:
            raise ValueError(f"Hour {h}: charging forbidden by no_charge_window")
        if h in constraints.no_discharge_hours and entry.battery_action == "discharge" and entry.battery_kwh > TOL:
            raise ValueError(f"Hour {h}: discharging forbidden by no_discharge_window")

        cap_h = constraints.max_grid_kwh_per_hour[h]
        if cap_h is not None and entry.grid_kwh > cap_h + TOL:
            raise ValueError(
                f"Hour {h}: grid_kwh {entry.grid_kwh} exceeds cap {cap_h}"
            )

        discharge = entry.battery_kwh if entry.battery_action == "discharge" else 0.0
        charge = entry.battery_kwh if entry.battery_action == "charge" else 0.0
        lhs = entry.grid_kwh + entry.solar_used_kwh + discharge
        rhs = src.demand_kwh + charge
        if abs(lhs - rhs) > TOL:
            raise ValueError(
                f"Hour {h}: energy balance violated: {lhs} != {rhs}"
            )

        expected_after = prev_energy + charge - discharge
        if abs(entry.battery_energy_after_kwh - expected_after) > TOL:
            raise ValueError(
                f"Hour {h}: battery state mismatch: reported "
                f"{entry.battery_energy_after_kwh}, expected {expected_after}"
            )

        lower = constraints.min_battery_energy_kwh[h] - TOL
        upper = cap + TOL
        if not (lower <= entry.battery_energy_after_kwh <= upper):
            raise ValueError(
                f"Hour {h}: battery energy {entry.battery_energy_after_kwh} outside "
                f"[{constraints.min_battery_energy_kwh[h]}, {cap}]"
            )

        total_grid += entry.grid_kwh
        total_cost += entry.grid_kwh * src.tariff_bdt_per_kwh
        peak_grid = max(peak_grid, entry.grid_kwh)

        prev_energy = entry.battery_energy_after_kwh

    if abs(prev_energy - init_e) > TOL:
        raise ValueError(
            f"Final battery energy {prev_energy} != initial {init_e}"
        )

    totals = {
        "total_grid_kwh": round(total_grid, 6),
        "total_cost_bdt": round(total_cost, 6),
        "peak_grid_kwh": round(peak_grid, 6),
    }
    return ordered, totals