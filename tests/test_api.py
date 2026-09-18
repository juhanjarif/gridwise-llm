from unittest.mock import patch

import pulp
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}

def test_optimize_returns_valid_plan():
    body = {
        "scenario_id": "T1",
        "operator_notes": ["nothing relevant"],
        "hours": [
            {"hour": h, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": 100, "initial_energy_kwh": 50,
            "minimum_energy_kwh": 10,
            "max_charge_kwh_per_hour": 10,
            "max_discharge_kwh_per_hour": 10,
        },
    }
    r = client.post("/optimize-energy", json=body)
    assert r.status_code == 200
    data = r.json()
    assert data["scenario_id"] == "T1"
    assert len(data["directive_interpretation"]) == 1
    assert len(data["hourly_plan"]) == 24

def test_optimize_rejects_malformed_body():
    r = client.post("/optimize-energy", json={"scenario_id": "T1"})
    assert r.status_code == 422

def test_pulp_solver_error_returns_controlled_422():
    # Regression: PulpSolverError doesn't inherit from RuntimeError, so an
    # infeasible LP used to slip past `except RuntimeError` as a raw,
    # unhandled 500 with a stack trace instead of a controlled 422.
    body = {
        "scenario_id": "T1",
        "operator_notes": ["nothing relevant"],
        "hours": [
            {"hour": h, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}
            for h in range(24)
        ],
        "battery": {
            "capacity_kwh": 100, "initial_energy_kwh": 50,
            "minimum_energy_kwh": 10,
            "max_charge_kwh_per_hour": 10,
            "max_discharge_kwh_per_hour": 10,
        },
    }
    with patch("app.main.solve", side_effect=pulp.PulpSolverError("simulated infeasible LP")):
        r = client.post("/optimize-energy", json=body)
    assert r.status_code == 422
    assert "simulated infeasible LP" in r.json()["detail"]