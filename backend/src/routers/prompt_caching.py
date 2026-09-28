"""HTTP API for the standalone expense-policy prompt-caching UI."""

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from src.services.prompt_caching import web_service


router = APIRouter(prefix="/api/prompt-caching", tags=["prompt-caching"])


class ClaimRequest(BaseModel):
    claim: str = Field(min_length=1, max_length=20_000)


@router.post("/policies")
async def create_policy(file: UploadFile = File(...)):
    name = file.filename or "expense_policy.pdf"
    if not name.lower().endswith(".pdf"):
        raise HTTPException(400, "Upload an expense-policy PDF file.")
    try:
        return web_service.create_policy_cache(name, await file.read())
    except web_service.PromptCacheError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/policies/{session_id}/claims")
def submit_claim(session_id: str, body: ClaimRequest):
    try:
        return web_service.check_claim(session_id, body.claim)
    except web_service.PromptCacheError as exc:
        raise HTTPException(400, str(exc)) from exc
