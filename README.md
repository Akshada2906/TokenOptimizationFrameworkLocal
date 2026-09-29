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

This is a separate React app. With the backend running:

```text
cd prompt-caching-frontend && npm install && npm run dev
```

Open `http://localhost:5174`.
Upload a selectable-text expense-policy PDF, create its Gemini explicit cache, then enter
claims one at a time. The UI shows only the cached-path response and measured cached/new token
usage.

```text
PROMPT_CACHE_MODEL=gemini-2.5-flash
PROMPT_CACHE_TTL_S=3600
```
