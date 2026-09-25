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
