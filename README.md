# Gridwise-LLM

Smart-campus energy optimization service. Given a 24-hour energy scenario plus 1-3 natural-language operator notes, it returns a machine-checkable interpretation of those notes and a valid, cost-minimized 24-hour battery grid schedule.

This README covers running and testing this implementation.

## Architecture

```
Energy Data + Operator Notes
        |
        v
  LLM Interpreter        -- Gemini/Groq call, untrusted output
        |
        v
  Guardrail Validator    -- deterministic schema check; anything
        |                    malformed/invented falls back to no_op
        v
  Optimizer              -- LP via PuLP/CBC, minimizes grid cost
        |
        v
  Replay Validator        -- independently re-checks the final plan
        |                    against every constraint before returning
        v
   API Response
```

- **LLM role**: interprets each operator note into one of six directive
  types (or `no_op`). Its raw output is never trusted directly.
- **Guardrails**: `app/guardrails/validator.py` re-validates every
  interpretation against `app/schemas.py` before it can reach the
  optimizer; anything malformed is safely coerced to `no_op`.
- **Optimizer**: `app/optimizer/directives.py` + `app/optimizer/solver.py`
  turn validated directives into constraints and solve for minimum grid
  cost using [PuLP](https://coin-or.github.io/pulp/)'s bundled CBC solver.
- **Replay validator**: `app/optimizer/replay.py` independently recomputes
  energy balance, battery bounds, and end-of-day neutrality from the
  solver's own output before it's returned.

## Setup (clean environment quickstart)

### Clone Github Repository

```bash
git clone https://github.com/juhanjarif/gridwise-llm
cd gridwise-llm
```

### Create Virtual Environment

#### For Windows CMD

```bash
python -m venv .venv
.venv\Scripts\activate.bat
```

#### For Windows Git Bash

```bash
python -m venv .venv
source .venv/Scripts/activate
```

#### For macOS/Linux

```bash
python -m venv .venv
source .venv/bin/activate
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

### Configure Environment Variables

```bash
cp .env.example .env
```

Then edit `.env` and fill in at least one API key. `.env` is gitignored —
no secret values are ever committed to this repository.

| Variable         | Required                | Purpose                                                    |
| ---------------- | ----------------------- | ---------------------------------------------------------- |
| `LLM_PROVIDER`   | Yes                     | Primary provider: `gemini` or `groq`                       |
| `GEMINI_API_KEY` | At least one of the two | Gemini API key (used if primary, or as automatic fallback) |
| `GROQ_API_KEY`   | At least one of the two | Groq API key (used if primary, or as automatic fallback)   |
| `PORT`           | No (default `8000`)     | Port the service listens on                                |

## Running the service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Testing

```bash
pytest tests/ -v
```

To verify the full pipeline end-to-end against a **running** instance
(the same way the hidden judge checks it — replaying each response
against the organizer's ground-truth directives, not just the returned
interpretation):

```bash
python -m tests.run_public_samples --base-url http://localhost:8000
```

Expected output ends with `ALL PASSED`.

## API examples

```bash
curl http://localhost:8000/health
```

```bash
curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d @data/example_request.json
```

## Deployment

Live public endpoint: `https://gridwise-llm-v1.onrender.com`

```bash
curl https://gridwise-llm-v1.onrender.com/health
```

## Docker fallback image

To use it locally:

```bash
docker build -t gridwise-llm:test .

docker run -d --name gridwise -p 8000:8000 \
  -e LLM_PROVIDER=gemini \
  -e GEMINI_API_KEY=<your-key> \
  -e GROQ_API_KEY=<your-key> \
  gridwise-llm:test

curl http://localhost:8000/health
```

**Pullable registry image:** `tamajose/gridwise-llm:v1`

```bash
docker pull tamajose/gridwise-llm:v1

docker run -d -p 8000:8000 \
  -e LLM_PROVIDER=gemini \
  -e GEMINI_API_KEY=<your-key> \
  -e GROQ_API_KEY=<your-key> \
  tamajose/gridwise-llm:v1
```

## Dependencies

See `requirements.txt`.

## Known Limitations

- The optimizer's LP has no round-trip battery efficiency loss, so
  charging and discharging in the same hour can be financially
  interchangeable; these are netted into a single action after solving
  rather than treated as an error.
- Both LLM providers' free tiers can rate-limit under heavy request
  volume in a short window; a retry-with-backoff handles transient 429s,
  but sustained throttling on both providers at once would still degrade
  affected notes to `no_op`.
- Directive interpretation depends on the configured LLM's judgment on
  paraphrased/unseen wording; guardrails reject anything that doesn't
  match the required schema, but cannot correct a wrong interpretation
  that happens to be well-formed.
