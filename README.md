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
