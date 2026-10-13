"""Hybrid policy-cache sessions used by the React expense-checker POC."""

from __future__ import annotations

import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from src.config.settings import settings
from src.services.prompt_caching.hybrid_policy import build_hybrid_policy, content_from_manifest
from src.services.prompt_caching.reviewer import create_structured_client, review_claim


SYSTEM_INSTRUCTION = """You are an employee expense-policy assistant. Use only the ordered
policy context cached with this request. Treat PixelPrompt prose and table images as text, and
use original visual crops for diagrams, arrows, receipts, and other visual evidence.

For a policy question, answer directly and cite PDF pages or section names when available. For
an expense claim, classify it as Compliant, Non-compliant, or Needs review and cite the controlling
policy. Never invent missing facts, approvals, receipts, currencies, exceptions, or visual details.
If the cached evidence does not answer a question, say so clearly."""


class PromptCacheError(Exception):
    pass


@dataclass
class PolicyCacheSession:
    id: str
    source_name: str
    pdf_path: Path
    manifest: list[dict[str, Any]]
    pages: int
    extracted_characters: int
    text_images: int
    table_images: int
    visual_images: int
    total_images: int
    preparation_s: float
    policy_tokens: int
    cache_context_tokens: int
    cache_name: str
    created_at: float
    expires_at: float
    renewals: int = 0
    claims: list[dict[str, Any]] = field(default_factory=list)
    questions: list[dict[str, Any]] = field(default_factory=list)
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
    global _structured_client
    if _structured_client is None:
        _structured_client = create_structured_client(_client_instance())
    return _structured_client


def _usage(response: Any) -> dict[str, int]:
    metadata = getattr(response, "usage_metadata", None)
    prompt_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
    cached_tokens = int(getattr(metadata, "cached_content_token_count", 0) or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "new_input_tokens": max(prompt_tokens - cached_tokens, 0),
        "output_tokens": int(getattr(metadata, "candidates_token_count", 0) or 0),
        "input_tokens_saved": cached_tokens,
    }


def _delete_remote_cache(cache_name: str) -> None:
    try:
        _client_instance().caches.delete(name=cache_name)
    except Exception:
        pass


def _create_remote_cache(manifest: list[dict[str, Any]]) -> tuple[str, int, int]:
    client = _client_instance()
    contents = content_from_manifest(manifest)
    counted = client.models.count_tokens(model=_model(), contents=contents)
    policy_tokens = int(getattr(counted, "total_tokens", 0) or 0)
    cache = client.caches.create(
        model=_model(),
        config=types.CreateCachedContentConfig(
            contents=contents,
            system_instruction=SYSTEM_INSTRUCTION,
            ttl=f"{settings.prompt_cache_ttl_s}s",
        ),
    )
    metadata = getattr(cache, "usage_metadata", None)
    context_tokens = int(getattr(metadata, "total_token_count", 0) or policy_tokens)
    return cache.name, policy_tokens, context_tokens


def _renew_cache(session: PolicyCacheSession) -> None:
    old_name = session.cache_name
    try:
        name, policy_tokens, context_tokens = _create_remote_cache(session.manifest)
    except Exception as exc:
        raise PromptCacheError(f"Gemini could not recreate the expired policy cache: {exc}") from exc
    now = time.time()
    session.cache_name = name
    session.policy_tokens = policy_tokens
    session.cache_context_tokens = context_tokens
    session.created_at = now
    session.expires_at = now + settings.prompt_cache_ttl_s
    session.renewals += 1
    _delete_remote_cache(old_name)


def _expired_cache_error(exc: Exception) -> bool:
    message = str(exc).lower()
    mentions_cache = "cachedcontent" in message or "cached content" in message
    return mentions_cache and any(word in message for word in ("expired", "not found", "invalid"))


def create_policy_cache(filename: str, pdf_bytes: bytes) -> dict[str, Any]:
    limit = settings.prompt_cache_max_pdf_mb * 1024 * 1024
    if not pdf_bytes:
        raise PromptCacheError("Choose a policy PDF before creating a cache.")
    if len(pdf_bytes) > limit:
        raise PromptCacheError(f"PDF is too large. Limit: {settings.prompt_cache_max_pdf_mb} MB.")
    sid = uuid.uuid4().hex
    folder = settings.workspace_root / "expense-policy-caches" / sid
    pdf_path = folder / (Path(filename).name or "expense_policy.pdf")
    generated_dir = folder / "ordered_images"
    folder.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(pdf_bytes)
    started = time.perf_counter()
    try:
        hybrid = build_hybrid_policy(pdf_path, generated_dir)
        preparation_s = time.perf_counter() - started
        cache_name, policy_tokens, context_tokens = _create_remote_cache(hybrid["manifest"])
    except Exception as exc:
        shutil.rmtree(folder, ignore_errors=True)
        if isinstance(exc, PromptCacheError):
            raise
        raise PromptCacheError(f"Could not prepare and cache this PDF: {exc}") from exc
    now = time.time()
    session = PolicyCacheSession(
        id=sid,
        source_name=pdf_path.name,
        pdf_path=pdf_path,
        manifest=hybrid["manifest"],
        pages=hybrid["pages"],
        extracted_characters=hybrid["extracted_characters"],
        text_images=hybrid["text_images"],
        table_images=hybrid["table_images"],
        visual_images=hybrid["visual_images"],
        total_images=hybrid["total_images"],
        preparation_s=preparation_s,
        policy_tokens=policy_tokens,
        cache_context_tokens=context_tokens,
        cache_name=cache_name,
        created_at=now,
        expires_at=now + settings.prompt_cache_ttl_s,
    )
    with _store_lock:
        _sessions[sid] = session
    return session_details(session)


def create_demo_policy_cache() -> dict[str, Any]:
    path = Path(__file__).with_name("data") / "Employee_Expense_Policy_POC_100p.pdf"
    if not path.is_file():
        raise PromptCacheError("The bundled 100-page demo policy is missing.")
    return create_policy_cache(path.name, path.read_bytes())


def _session(session_id: str) -> PolicyCacheSession:
    with _store_lock:
        session = _sessions.get(session_id)
    if not session:
        raise PromptCacheError("Policy session not found. Create or upload a policy first.")
    with session.lock:
        if time.time() >= session.expires_at - 5:
            _renew_cache(session)
    return session


def session_details(session: PolicyCacheSession) -> dict[str, Any]:
    return {
        "session_id": session.id,
        "source_name": session.source_name,
        "pages": session.pages,
        "extracted_characters": session.extracted_characters,
        "text_images": session.text_images,
        "table_images": session.table_images,
        "visual_images": session.visual_images,
        "total_images": session.total_images,
        "preparation_s": round(session.preparation_s, 3),
        "policy_tokens": session.policy_tokens,
        "cache_context_tokens": session.cache_context_tokens,
        "model": _model(),
        "ttl_seconds": settings.prompt_cache_ttl_s,
        "expires_at": session.expires_at,
        "cache_renewals": session.renewals,
        "claims_processed": len(session.claims),
        "questions_answered": len(session.questions),
    }


def ask_policy(session_id: str, question: str) -> dict[str, Any]:
    if not question.strip():
        raise PromptCacheError("Enter a policy question before submitting.")
    session = _session(session_id)
    with session.lock:
        started = time.perf_counter()
        def generate() -> Any:
            return _client_instance().models.generate_content(
                model=_model(),
                contents=[types.Content(role="user", parts=[types.Part(text=question.strip())])],
                config=types.GenerateContentConfig(temperature=0, cached_content=session.cache_name),
            )

        try:
            response = generate()
        except Exception as exc:
            if not _expired_cache_error(exc):
                raise PromptCacheError(f"Gemini could not answer this policy question: {exc}") from exc
            _renew_cache(session)
            try:
                response = generate()
            except Exception as retry_exc:
                raise PromptCacheError(f"Gemini could not answer this policy question: {retry_exc}") from retry_exc
        usage = _usage(response)
        session.questions.append({"usage": usage})
        return {
            "answer": response.text or "",
            "usage": usage,
            "latency_s": round(time.perf_counter() - started, 3),
            "session": session_details(session),
        }


def check_claim(session_id: str, claim: str) -> dict[str, Any]:
    if not claim.strip():
        raise PromptCacheError("Enter an expense claim before submitting.")
    session = _session(session_id)
    with session.lock:
        started = time.perf_counter()
        def classify() -> tuple[Any, Any]:
            return review_claim(
                _structured_client_instance(), _model(), claim, cached_content=session.cache_name
            )

        try:
            answer, response = classify()
        except Exception as exc:
            if not _expired_cache_error(exc):
                raise PromptCacheError(f"Gemini could not check this claim: {exc}") from exc
            _renew_cache(session)
            try:
                answer, response = classify()
            except Exception as retry_exc:
                raise PromptCacheError(f"Gemini could not check this claim: {retry_exc}") from retry_exc
        usage = _usage(response)
        session.claims.append({"usage": usage})
        return {
            "answer": answer.model_dump(),
            "usage": usage,
            "latency_s": round(time.perf_counter() - started, 3),
            "session": session_details(session),
        }
