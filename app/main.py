from fastapi import FastAPI, HTTPException
from app.schemas import (HealthResponse, OptimizeEnergyRequest, OptimizeEnergyResponse, DirectiveInterpretation)
from app.llm.interpreter import (interpret_notes, InterpretationUnavailableError, MalformedLLMOutputError)
from app.guardrails.validator import validate_interpretations
from app.optimizer import build_constraints, solve, replay_and_verify

app = FastAPI(title="GridWise LLM Assistant")

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")

@app.post("/optimize-energy", response_model=OptimizeEnergyResponse)
async def optimize_energy(req: OptimizeEnergyRequest):
    try:
        raw_directives = await interpret_notes(
            req.operator_notes,
            req.battery.capacity_kwh,
            timeout=20.0,
        )
    except (InterpretationUnavailableError, MalformedLLMOutputError) as exc:
        directives = [
            DirectiveInterpretation(
                note_index=i,
                applies=False,
                directive_type="no_op",
                structured_adjustment=None,
                explanation=f"LLM unavailable: {exc}",
            )
            for i in range(len(req.operator_notes))
        ]
    else:
        directives = validate_interpretations(raw_directives, len(req.operator_notes))

    constraints = build_constraints(req.hours, req.battery, directives)

    try:
        plan = solve(req.hours, req.battery, constraints)
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        plan, totals = replay_and_verify(req.hours, req.battery, plan, constraints)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=f"Internal plan invalid: {exc}")

    return OptimizeEnergyResponse(
        scenario_id=req.scenario_id,
        directive_interpretation=directives,
        hourly_plan=plan,
        total_grid_kwh=totals["total_grid_kwh"],
        total_cost_bdt=totals["total_cost_bdt"],
        peak_grid_kwh=totals["peak_grid_kwh"],
        plan_summary="Applied operator directives and minimized grid cost.",
    )