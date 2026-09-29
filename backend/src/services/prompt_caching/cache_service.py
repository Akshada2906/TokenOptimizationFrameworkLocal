"""In-memory policy-cache sessions used by the React expense-checker POC."""

from __future__ import annotations

import io
import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from pypdf import PdfReader

from src.config.settings import settings
from src.services.prompt_caching.reviewer import (
    SYSTEM_INSTRUCTION,
    create_structured_client,
    review_claim,
)


class PromptCacheError(Exception):
    pass


@dataclass
class PolicyCacheSession:
    id: str
    source_name: str
    pdf_path: Path
    pages: int
    extracted_characters: int
    policy_tokens: int
    cache_context_tokens: int
    cache_name: str
    created_at: float
    expires_at: float
    claims: list[dict[str, Any]] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)


_sessions: dict[str, PolicyCacheSession] = {}
_store_lock = threading.RLock()
_client: genai.Client | None = None
_structured_client: Any | None = None


def _model() -> str:
    return settings.prompt_cache_model or settings.gemini_model


def _client_instance() -> genai.Client:
    global _client
    if not settings.gemini_api_key:
        raise PromptCacheError("GEMINI_API_KEY is not configured on the server.")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _structured_client_instance() -> Any:
    """Return the Gemini client wrapped by Instructor for Pydantic validation/retries."""
    global _structured_client
    if _structured_client is None:
        _structured_client = create_structured_client(_client_instance())
    return _structured_client


def _content(policy_text: str) -> list[types.Content]:
    return [
        types.Content(role="user", parts=[types.Part(text="Expense policy to apply:\n\n" + policy_text)]),
        types.Content(role="model", parts=[types.Part(text="I will apply this policy exactly to each claim.")]),
    ]


def _extract_pdf(upload: bytes) -> tuple[str, int]:
    try:
        reader = PdfReader(io.BytesIO(upload))
        text = "\n\n".join((page.extract_text() or "").strip() for page in reader.pages).strip()
    except Exception as exc:
        raise PromptCacheError(f"Could not read this PDF: {exc}") from exc
    if len(text) < 1_000:
        raise PromptCacheError("This PDF has too little selectable text. Use a text PDF or OCR it before upload.")
    return text, len(reader.pages)


def _usage(response: Any) -> dict[str, int]:
    metadata = getattr(response, "usage_metadata", None)
    prompt_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
    cached_tokens = int(getattr(metadata, "cached_content_token_count", 0) or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "new_input_tokens": max(prompt_tokens - cached_tokens, 0),
        "output_tokens": int(getattr(metadata, "candidates_token_count", 0) or 0),
    }


def _delete_remote_cache(cache_name: str) -> None:
    try:
        _client_instance().caches.delete(name=cache_name)
    except Exception:
        # Remote cache deletion is best-effort: Gemini TTL remains the final safeguard.
        pass


def _clean_expired() -> None:
    now = time.time()
    with _store_lock:
        expired = [sid for sid, session in _sessions.items() if now >= session.expires_at]
        for sid in expired:
            session = _sessions.pop(sid)
            _delete_remote_cache(session.cache_name)
            shutil.rmtree(session.pdf_path.parent, ignore_errors=True)


def create_policy_cache(filename: str, pdf_bytes: bytes) -> dict[str, Any]:
    _clean_expired()
    limit = settings.prompt_cache_max_pdf_mb * 1024 * 1024
    if not pdf_bytes:
        raise PromptCacheError("Choose a policy PDF before creating a cache.")
    if len(pdf_bytes) > limit:
        raise PromptCacheError(f"PDF is too large. Limit: {settings.prompt_cache_max_pdf_mb} MB.")
    policy_text, pages = _extract_pdf(pdf_bytes)
    sid = uuid.uuid4().hex
    folder = settings.workspace_root / "expense-policy-caches" / sid
    pdf_path = folder / (Path(filename).name or "expense_policy.pdf")
    folder.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)
    client = _client_instance()
    contents = _content(policy_text)
    try:
        counted = client.models.count_tokens(model=_model(), contents=contents)
        policy_tokens = int(getattr(counted, "total_tokens", 0) or 0)
        cache = client.caches.create(
            model=_model(),
            config=types.CreateCachedContentConfig(
                contents=contents, system_instruction=SYSTEM_INSTRUCTION, ttl=f"{settings.prompt_cache_ttl_s}s"
            ),
        )
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise PromptCacheError(f"Gemini could not create the policy cache: {exc}") from exc
    cache_usage = getattr(cache, "usage_metadata", None)
    cached_context_tokens = int(getattr(cache_usage, "total_token_count", 0) or policy_tokens)
    now = time.time()
    session = PolicyCacheSession(
        id=sid,
        source_name=pdf_path.name,
        pdf_path=pdf_path,
        pages=pages,
        extracted_characters=len(policy_text),
        policy_tokens=policy_tokens,
        cache_context_tokens=cached_context_tokens,
        cache_name=cache.name,
        created_at=now,
        expires_at=now + settings.prompt_cache_ttl_s,
    )
    with _store_lock:
        _sessions[sid] = session
    return session_details(session)


def _session(session_id: str) -> PolicyCacheSession:
    _clean_expired()
    with _store_lock:
        session = _sessions.get(session_id)
    if not session:
        raise PromptCacheError("Policy cache session not found or expired. Upload the policy again.")
    return session


def session_details(session: PolicyCacheSession) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "source_name": session.source_name,
        "pages": session.pages,
        "extracted_characters": session.extracted_characters,
        "policy_tokens": session.policy_tokens,
        "cache_context_tokens": session.cache_context_tokens,
        "model": _model(),
        "ttl_seconds": settings.prompt_cache_ttl_s,
        "expires_at": session.expires_at,
        "claims_processed": len(session.claims),
    }


def check_claim(session_id: str, claim: str) -> dict[str, Any]:
    if not claim.strip():
        raise PromptCacheError("Enter an expense claim before submitting.")
    session = _session(session_id)
    with session.lock:
        started = time.perf_counter()
        try:
            answer, response = review_claim(
                _structured_client_instance(),
                _model(),
                claim,
                cached_content=session.cache_name,
            )
        except Exception as exc:
            raise PromptCacheError(f"Gemini could not check this claim: {exc}") from exc
        elapsed_s = time.perf_counter() - started
        usage = _usage(response)
        session.claims.append({"usage": usage, "output_tokens": usage["output_tokens"]})
        return {
            "answer": answer.model_dump(),
            "usage": usage,
            "latency_s": round(elapsed_s, 3),
            "session": session_details(session),
        }
