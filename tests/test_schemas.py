import pytest
from pydantic import ValidationError
from app.schemas import (
    DirectiveInterpretation,
    SolarReductionAdjustment,
    OptimizeEnergyRequest,
)

def test_solar_reduction_valid():
    d = DirectiveInterpretation(
        note_index=0,
        applies=True,
        directive_type="solar_reduction",
        structured_adjustment={"hours": [12, 13], "factor": 0.25},
        explanation="Panel cleaning.",
    )
    assert d.structured_adjustment["factor"] == 0.25

def test_no_op_valid():
    d = DirectiveInterpretation(
        note_index=1,
        applies=False,
        directive_type="no_op",
        structured_adjustment=None,
        explanation="Irrelevant.",
    )
    assert d.applies is False

def test_no_op_rejects_applies_true():
    with pytest.raises(ValidationError):
        DirectiveInterpretation(
            note_index=1,
            applies=True,
            directive_type="no_op",
            structured_adjustment=None,
        )

def test_non_no_op_requires_applies_true():
    with pytest.raises(ValidationError):
        DirectiveInterpretation(
            note_index=0,
            applies=False,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12], "factor": 0.5},
        )

def test_hours_must_be_ascending():
    with pytest.raises(ValidationError):
        SolarReductionAdjustment(hours=[13, 12], factor=0.5)

def test_hours_must_be_unique():
    with pytest.raises(ValidationError):
        SolarReductionAdjustment(hours=[12, 12], factor=0.5)

def test_hours_must_be_in_range():
    with pytest.raises(ValidationError):
        SolarReductionAdjustment(hours=[24], factor=0.5)

def test_factor_must_be_within_0_1():
    with pytest.raises(ValidationError):
        SolarReductionAdjustment(hours=[12], factor=1.5)

def test_wrong_adjustment_shape_for_type():
    with pytest.raises(ValidationError):
        DirectiveInterpretation(
            note_index=0,
            applies=True,
            directive_type="solar_reduction",
            structured_adjustment={"hours": [12]},
        )

def test_extra_keys_rejected():
    with pytest.raises(ValidationError):
        SolarReductionAdjustment(hours=[12], factor=0.5, bogus=1)

def _valid_hours():
    return [
        {"hour": h, "demand_kwh": 100, "solar_kwh": 0, "tariff_bdt_per_kwh": 5}
        for h in range(24)
    ]

def test_request_requires_24_hours():
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(
            scenario_id="X",
            operator_notes=["note"],
            hours=_valid_hours()[:23],   # ← only 23
            battery={
                "capacity_kwh": 100, "initial_energy_kwh": 50,
                "minimum_energy_kwh": 10,
                "max_charge_kwh_per_hour": 10,
                "max_discharge_kwh_per_hour": 10,
            },
        )

def test_request_rejects_blank_notes():
    with pytest.raises(ValidationError):
        OptimizeEnergyRequest(
            scenario_id="X",
            operator_notes=["   "],
            hours=_valid_hours(),
            battery={
                "capacity_kwh": 100, "initial_energy_kwh": 50,
                "minimum_energy_kwh": 10,
                "max_charge_kwh_per_hour": 10,
                "max_discharge_kwh_per_hour": 10,
            },
        )