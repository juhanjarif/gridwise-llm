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