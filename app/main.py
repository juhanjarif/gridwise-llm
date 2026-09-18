from fastapi import FastAPI, HTTPException
from app.schemas import HealthResponse, OptimizeEnergyRequest, OptimizeEnergyResponse

app = FastAPI(title="GridWise LLM Assistant")

@app.get("/health", response_model=HealthResponse)
def health():
    return HealthResponse(status="ok")

@app.post("/optimize-energy", response_model=OptimizeEnergyResponse)
def optimize_energy(req: OptimizeEnergyRequest):
    raise HTTPException(status_code=501, detail="Not implemented yet")