# GridWise LLM — BUP CSE Fest 2026 Preliminary

Smart-campus energy optimization service. Given a 24-hour energy scenario
plus 1-3 natural-language operator notes, it returns a machine-checkable
interpretation of those notes and a valid, cost-minimized 24-hour battery
+ grid schedule.

Full behavior is defined by the organizer's Problem Statement; this README
only covers running and testing this implementation.

## Architecture

```
Energy Data + Operator Notes
        |
        v
  LLM Interpreter  (app/llm/)        -- Gemini/Groq call, untrusted output
        |
        v
  Guardrail Validator (app/guardrails/) -- deterministic schema check,
        |                                  unsafe/invented directives ->
        |                                  fall back to no_op
        v
  Math Optimizer  (app/optimizer/)   -- LP via PuLP/CBC, minimizes grid cost
        |
        v
  Final Validator (app/optimizer/replay.py) -- independently replays the
        |                                       plan against every
        |                                       constraint before returning
        v
   API Response
```

- **LLM role**: interprets each operator note into one of six directive
  types (or `no_op`). Its raw output is never trusted directly.
- **Guardrails**: `app/guardrails/validator.py` re-validates every
  interpretation against the exact schema in `app/schemas.py` (directive
  type, hour ranges, numeric bounds, `applies`/`no_op` consistency). Any
  entry that doesn't fit — missing, duplicated, invented type, wrong
  adjustment shape — is safely coerced to `no_op` instead of crashing the
  request or reaching the optimizer.
- **Optimizer**: `app/optimizer/directives.py` turns validated directives
  into effective constraints (adjusted solar, reserve floors, no-charge/
  no-discharge hours, grid caps); `app/optimizer/solver.py` solves the
  resulting linear program with [PuLP](https://coin-or.github.io/pulp/)'s
  bundled CBC solver to minimize total grid cost.
- **Replay/final validator**: `app/optimizer/replay.py` independently
  recomputes energy balance, battery bounds, rate limits, and end-of-day
  neutrality from the solver's own output before it's returned — the same
  checks the hidden judge performs.

## Model / provider

Two providers are supported, with automatic fallback if the primary one
fails (timeout, HTTP error, rate limit, missing key):

| Env var | Purpose |
|---|---|
| `LLM_PROVIDER` | Primary provider: `gemini` or `groq` |
| `GEMINI_API_KEY` | Gemini API key (used if `LLM_PROVIDER=gemini`, or as fallback) |
| `GROQ_API_KEY` | Groq API key (used if `LLM_PROVIDER=groq`, or as fallback) |
| `GEMINI_MODEL` | Optional override, defaults to `gemini-3.6-flash` |
| `GROQ_MODEL` | Optional override, defaults to `openai/gpt-oss-120b` |
| `PORT` | Port the service listens on (default `8000`) |
| `LOG_LEVEL` | Optional, defaults to `INFO` |

Whichever provider is set in `LLM_PROVIDER` is tried first; if it fails,
the other provider is tried automatically as long as its API key is
configured. At least one of `GEMINI_API_KEY` / `GROQ_API_KEY` must be set
for the LLM requirement to be satisfied.

## Setup (clean environment quickstart)

```bash
git clone <this-repo-url>
cd gridwise-llm

python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash
# .venv\Scripts\activate.bat       # Windows cmd.exe
# source .venv/bin/activate        # macOS/Linux

pip install -r requirements.txt

cp .env.example .env
# then edit .env and fill in GEMINI_API_KEY and/or GROQ_API_KEY
```

`.env` is never committed (see `.gitignore`) — no secret values appear
anywhere in this repository.

## Running the service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Testing

```bash
# Guardrail + schema + optimizer + API unit tests (no network calls, no API keys needed)
pytest tests/ -v

# End-to-end: run all 10 public sample cases against a REAL running service
# (needs a valid API key configured, and the service running per above)
python -m tests.run_public_samples --base-url http://localhost:8000
```

`tests/run_public_samples.py` posts each case in
`data/public_samples.json` to the live `/optimize-energy` endpoint, then
independently replays the response against the case's organizer
ground-truth directives — the same check the hidden judge performs — so a
service that gets the interpretation right but ignores it downstream will
still fail here.

## API examples

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

```bash
curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d @data/example_request.json
```

`data/example_request.json` is SAMPLE-02's real input (verified against a
running instance of this service: it returns `total_grid_kwh: 2915`,
`total_cost_bdt: 42885`, matching the organizer's expected output exactly).
Every other public case's full request body is in
`data/public_samples.json`.

## Dependencies

See `requirements.txt`. Notably:
- `fastapi` + `uvicorn` — HTTP service
- `pydantic` — request/response schema validation and the deterministic
  guardrail checks
- `httpx` — LLM provider HTTP calls
- `pulp` — linear-programming optimizer (bundled CBC solver, no external
  binary required)
- `python-dotenv` — loads `.env` in `app/config.py`

## Known limitations

- The optimizer models the battery with no round-trip efficiency loss;
  charge/discharge in the same hour are financially interchangeable
  whenever they net to the same result, so the solver may occasionally
  produce a solution with tiny nonzero values in both variables for one
  hour. This is netted into a single `charge`/`discharge`/`idle` action
  before being returned (see the comment in `app/optimizer/solver.py`) —
  it does not affect correctness, only which of the two labels is used.
- LLM calls have their own provider-side latency and rate limits; both
  configured providers' free tiers can be rate-limited under heavy
  request volume in a short window.
- Directive interpretation depends on the configured LLM's judgment on
  paraphrased/unseen wording; guardrails reject anything that doesn't fit
  the required schema, but cannot fix a genuinely wrong interpretation
  that happens to be well-formed.
