"""Pydantic models for the /optimize-energy request/response contract.

Source of truth: Preliminary Problem Statement, Sections 04, 07, 10.
"""

from __future__ import annotations

from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


def _validate_hours(hours: list[int]) -> list[int]:
    if not hours:
        raise ValueError("hours must be a non-empty list")
    if any(h < 0 or h > 23 for h in hours):
        raise ValueError("hours must be integers from 0 through 23")
    if len(set(hours)) != len(hours):
        raise ValueError("hours must not contain duplicates")
    if hours != sorted(hours):
        raise ValueError("hours must be in ascending order")
    return hours


# ---------------------------------------------------------------------------
# Request schema (Problem Statement §07)
# ---------------------------------------------------------------------------

class HourEntry(BaseModel):
    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0)
    solar_kwh: float = Field(ge=0)
    tariff_bdt_per_kwh: float = Field(ge=0)


class BatteryConfig(BaseModel):
    capacity_kwh: float = Field(gt=0)
    initial_energy_kwh: float = Field(ge=0)
    minimum_energy_kwh: float = Field(ge=0)
    max_charge_kwh_per_hour: float = Field(ge=0)
    max_discharge_kwh_per_hour: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_bounds(self) -> "BatteryConfig":
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        if not (self.minimum_energy_kwh <= self.initial_energy_kwh <= self.capacity_kwh):
            raise ValueError("initial_energy_kwh must be between minimum_energy_kwh and capacity_kwh")
        return self


class OptimizeEnergyRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    operator_notes: list[str] = Field(min_length=1, max_length=3)
    hours: list[HourEntry] = Field(min_length=24, max_length=24)
    battery: BatteryConfig

    @model_validator(mode="after")
    def _check_hours(self) -> "OptimizeEnergyRequest":
        if any(not note.strip() for note in self.operator_notes):
            raise ValueError("operator_notes entries must be non-empty")
        hour_values = [h.hour for h in self.hours]
        if sorted(hour_values) != list(range(24)):
            raise ValueError("hours must contain exactly one entry for each hour 0 through 23")
        return self


# ---------------------------------------------------------------------------
# Directive types & structured_adjustment shapes (Problem Statement §04.1)
# ---------------------------------------------------------------------------

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]

ALLOWED_DIRECTIVE_TYPES = frozenset(
    {
        "solar_reduction",
        "minimum_battery_reserve",
        "no_charge_window",
        "no_discharge_window",
        "max_grid_window",
        "no_op",
    }
)


class _AdjustmentBase(BaseModel):
    # extra="forbid" matters here: several adjustment shapes share the same
    # required fields (e.g. no_charge_window vs no_discharge_window both have
    # only "hours"), so an unexpected extra field is often the only signal
    # that the LLM emitted the wrong shape for the chosen directive_type.
    model_config = {"extra": "forbid"}


class SolarReductionAdjustment(_AdjustmentBase):
    hours: list[int]
    factor: float = Field(ge=0, le=1)

    @model_validator(mode="after")
    def _check(self) -> "SolarReductionAdjustment":
        _validate_hours(self.hours)
        return self


class MinimumBatteryReserveAdjustment(_AdjustmentBase):
    hours: list[int]
    minimum_energy_kwh: float = Field(ge=0)

    @model_validator(mode="after")
    def _check(self) -> "MinimumBatteryReserveAdjustment":
        _validate_hours(self.hours)
        return self


class NoChargeWindowAdjustment(_AdjustmentBase):
    hours: list[int]

    @model_validator(mode="after")
    def _check(self) -> "NoChargeWindowAdjustment":
        _validate_hours(self.hours)
        return self


class NoDischargeWindowAdjustment(_AdjustmentBase):
    hours: list[int]

    @model_validator(mode="after")
    def _check(self) -> "NoDischargeWindowAdjustment":
        _validate_hours(self.hours)
        return self


class MaxGridWindowAdjustment(_AdjustmentBase):
    hours: list[int]
    max_grid_kwh: float = Field(ge=0)

    @model_validator(mode="after")
    def _check(self) -> "MaxGridWindowAdjustment":
        _validate_hours(self.hours)
        return self


# Note: no_charge_window and no_discharge_window share the identical {"hours": [...]}
# shape, so a plain Union would resolve ambiguously. Instead, structured_adjustment is
# kept as a raw dict on the wire and validated against the model selected by
# directive_type below, rather than by Pydantic's own union-matching.
StructuredAdjustment = Union[
    SolarReductionAdjustment,
    MinimumBatteryReserveAdjustment,
    NoChargeWindowAdjustment,
    NoDischargeWindowAdjustment,
    MaxGridWindowAdjustment,
]

# Maps directive_type -> the model class that validates its structured_adjustment.
ADJUSTMENT_MODEL_BY_TYPE: dict[str, type[BaseModel]] = {
    "solar_reduction": SolarReductionAdjustment,
    "minimum_battery_reserve": MinimumBatteryReserveAdjustment,
    "no_charge_window": NoChargeWindowAdjustment,
    "no_discharge_window": NoDischargeWindowAdjustment,
    "max_grid_window": MaxGridWindowAdjustment,
}


class DirectiveInterpretation(BaseModel):
    note_index: int = Field(ge=0)
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: Optional[dict] = None
    explanation: str = ""

    @model_validator(mode="after")
    def _check_applies_semantics(self) -> "DirectiveInterpretation":
        if self.directive_type == "no_op":
            if self.applies is not False or self.structured_adjustment is not None:
                raise ValueError("no_op requires applies=false and structured_adjustment=null")
        else:
            if self.applies is not True:
                raise ValueError(f"{self.directive_type} requires applies=true")
            if self.structured_adjustment is None:
                raise ValueError(f"{self.directive_type} requires a structured_adjustment")
            expected_model = ADJUSTMENT_MODEL_BY_TYPE[self.directive_type]
            # Validate shape by construction, then normalize back to a plain dict
            # (rejects extra/missing fields and out-of-range values via the sub-model).
            validated = expected_model.model_validate(self.structured_adjustment)
            self.structured_adjustment = validated.model_dump()
        return self

    def adjustment_as_model(self) -> Optional[BaseModel]:
        """Return structured_adjustment parsed into its typed model, or None for no_op."""
        if self.directive_type == "no_op":
            return None
        expected_model = ADJUSTMENT_MODEL_BY_TYPE[self.directive_type]
        return expected_model.model_validate(self.structured_adjustment)


# ---------------------------------------------------------------------------
# Response schema (Problem Statement §10)
# ---------------------------------------------------------------------------

BatteryAction = Literal["charge", "discharge", "idle"]


class HourlyPlanEntry(BaseModel):
    hour: int = Field(ge=0, le=23)
    grid_kwh: float = Field(ge=0)
    solar_used_kwh: float = Field(ge=0)
    battery_action: BatteryAction
    battery_kwh: float = Field(ge=0)
    battery_energy_after_kwh: float = Field(ge=0)

    @model_validator(mode="after")
    def _check_idle(self) -> "HourlyPlanEntry":
        if self.battery_action == "idle" and self.battery_kwh != 0:
            raise ValueError("battery_kwh must be 0 when battery_action is idle")
        return self


class OptimizeEnergyResponse(BaseModel):
    scenario_id: str
    directive_interpretation: list[DirectiveInterpretation]
    hourly_plan: list[HourlyPlanEntry] = Field(min_length=24, max_length=24)
    total_grid_kwh: float = Field(ge=0)
    total_cost_bdt: float = Field(ge=0)
    peak_grid_kwh: float = Field(ge=0)
    plan_summary: str

    @model_validator(mode="after")
    def _check_hours_coverage(self) -> "OptimizeEnergyResponse":
        hour_values = [entry.hour for entry in self.hourly_plan]
        if sorted(hour_values) != list(range(24)):
            raise ValueError("hourly_plan must contain exactly one entry for each hour 0 through 23")
        return self


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
