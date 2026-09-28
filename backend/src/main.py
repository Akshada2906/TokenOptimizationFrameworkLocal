from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.config.settings import settings
from src.routers import prompt_caching, sessions

app = FastAPI(title="Token Optimization Framework")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(sessions.router)
app.include_router(prompt_caching.router)


@app.get("/health")
def health_check():
    return {"status": "ok"}
