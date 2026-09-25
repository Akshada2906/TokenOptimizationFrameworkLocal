from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    repo_url: str = Field(min_length=8, max_length=500)


class SessionCreated(BaseModel):
    session_id: str


class SessionStatus(BaseModel):
    session_id: str
    status: str
    error: str | None = None
    source: str
    stats: dict[str, Any] = {}


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    open_file: str | None = None


class ChatResponse(BaseModel):
    answer: str
    context_used: str
    stats: dict[str, Any]
    images_used: list[dict[str, Any]] = []


class FileContent(BaseModel):
    path: str
    content: str
