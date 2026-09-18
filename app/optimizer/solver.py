from __future__ import annotations

import pulp

from app.schemas import HourEntry, BatteryConfig, HourlyPlanEntry
from app.optimizer.directives import EffectiveConstraints

EPS = 1e-6


def solve(hours: list[HourEntry], battery: BatteryConfig, constraints: EffectiveConstraints) -> list[HourlyPlanEntry]:
    n = 24
    by_hour = {h.hour: h for h in hours}
    demand = [float(by_hour[h].demand_kwh) for h in range(n)]
    tariff = [float(by_hour[h].tariff_bdt_per_kwh) for h in range(n)]
    solar_cap = constraints.effective_solar_kwh
    min_batt = constraints.min_battery_energy_kwh
    cap = float(battery.capacity_kwh)
    max_chg = float(battery.max_charge_kwh_per_hour)
    max_dis = float(battery.max_discharge_kwh_per_hour)
    init_e = float(battery.initial_energy_kwh)
    grid_cap = constraints.max_grid_kwh_per_hour

    prob = pulp.LpProblem("gridwise_optimize", pulp.LpMinimize)

    grid = [pulp.LpVariable(f"grid_{h}", lowBound=0) for h in range(n)]
    sol = [pulp.LpVariable(f"solar_{h}", lowBound=0, upBound=solar_cap[h]) for h in range(n)]
    chg = [pulp.LpVariable(f"chg_{h}", lowBound=0, upBound=max_chg) for h in range(n)]
    dis = [pulp.LpVariable(f"dis_{h}", lowBound=0, upBound=max_dis) for h in range(n)]
    batt = [
        pulp.LpVariable(f"batt_{h}", lowBound=min_batt[h], upBound=cap)
        for h in range(n)
    ]

    prob += pulp.lpSum(grid[h] * tariff[h] for h in range(n))

    for h in range(n):
        prev = init_e if h == 0 else batt[h - 1]

        prob += grid[h] + sol[h] + dis[h] == demand[h] + chg[h]

        prob += batt[h] == prev + chg[h] - dis[h]

        if h in constraints.no_charge_hours:
            prob += chg[h] == 0
        if h in constraints.no_discharge_hours:
            prob += dis[h] == 0

        if grid_cap[h] is not None:
            prob += grid[h] <= grid_cap[h]

    prob += batt[n - 1] == init_e

    import shutil
    cbc_path = shutil.which("cbc")
    if cbc_path:
        solver = pulp.COIN_CMD(path=cbc_path, msg=False)
    else:
        solver = pulp.PULP_CBC_CMD(msg=False)

    try:
        status = prob.solve(solver)
    except Exception:
        status = prob.solve()

    if pulp.LpStatus[status] != "Optimal":
        raise RuntimeError(f"Optimizer did not find an optimal solution: {pulp.LpStatus[status]}")

    plan: list[HourlyPlanEntry] = []
    for h in range(n):
        g = _clean(grid[h].value())
        s = _clean(sol[h].value())
        c = _clean(chg[h].value())
        d = _clean(dis[h].value())
        b = _clean(batt[h].value())

        net = c - d
        if net > EPS:
            action, kwh = "charge", _clean(net)
        elif net < -EPS:
            action, kwh = "discharge", _clean(-net)
        else:
            action, kwh = "idle", 0.0

        plan.append(
            HourlyPlanEntry(
                hour=h,
                grid_kwh=g,
                solar_used_kwh=s,
                battery_action=action,
                battery_kwh=kwh,
                battery_energy_after_kwh=b,
            )
        )

    return plan

def _clean(x: float | None) -> float:
    if x is None:
        return 0.0
    if abs(x) < EPS:
        return 0.0
    return round(x, 6)