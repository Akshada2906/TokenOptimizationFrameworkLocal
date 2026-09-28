# RepoGraph (TokenOptimizationFramework)

Chat with a codebase for fewer tokens: the repo is analyzed once (Graphify dependency graph +
architecture scan), rendered into images with the `pixelprompt` library, and those images ground the assistant.

## Run
Backend (needs Graphviz `dot` for diagrams, `git`, and `GEMINI_API_KEY` in `backend/.env`):

    cd backend && python -m venv venv && source venv/bin/activate
    pip install -r requirements.txt
    uvicorn src.main:app --reload --port 8000

Frontend:

    cd frontend && npm install && npm run dev   # http://localhost:5173

## Expense-policy cache UI

With the backend and frontend running, open `http://localhost:5173/policy-cache`.
Upload a selectable-text expense-policy PDF, create its Gemini explicit cache, then enter
claims one at a time. The UI shows only the cached-path response, measured cached/new token
usage, a no-cache-equivalent estimate, and the session net after cache creation plus TTL storage.

The default cost assumptions target Gemini 2.5 Flash Standard paid-tier text pricing as checked
on 2026-09-28. Override them in `backend/.env` whenever the selected model or pricing tier changes:

```text
PROMPT_CACHE_MODEL=gemini-2.5-flash
PROMPT_CACHE_TTL_S=3600
PROMPT_CACHE_STANDARD_INPUT_USD_PER_M=0.30
PROMPT_CACHE_CACHED_INPUT_USD_PER_M=0.03
PROMPT_CACHE_OUTPUT_USD_PER_M=2.50
PROMPT_CACHE_STORAGE_USD_PER_M_TOKEN_HOUR=1.00
```
