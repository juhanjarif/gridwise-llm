Smart-campus energy optimization service. Given a 24-hour energy scenario plus 1-3 natural-language operator notes, it returns a machine-checkable interpretation of those notes and a valid, cost-minimized 24-hour battery grid schedule.

This README covers running and testing this implementation.

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

## Running the service

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Testing

```bash
pytest tests/ -v
```

## API examples

```bash
curl http://localhost:8000/health
```

```bash
curl -X POST http://localhost:8000/optimize-energy \
  -H "Content-Type: application/json" \
  -d @data/example_request.json
```
