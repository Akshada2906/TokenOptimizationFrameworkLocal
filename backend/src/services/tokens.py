"""Exact token accounting via Gemini count_tokens: images as sent vs. the same content as text."""
import logging
from pathlib import Path

from google.genai import types

from src.config.settings import settings

log = logging.getLogger(__name__)


def count_text(text: str) -> int:
    from src.services.chat import client  # local import avoids a cycle

    try:
        return client().models.count_tokens(model=settings.gemini_model, contents=text).total_tokens or 0
    except Exception as e:
        log.info("count_tokens failed for text, estimating: %s", e)
        return len(text) // 4


def count_images(paths: list[Path], batch: int = 25) -> int | None:
    """Exact image tokens via count_tokens, in batches to keep requests small."""
    from src.services.chat import client

    total = 0
    try:
        for i in range(0, len(paths), batch):
            parts = [types.Part.from_bytes(data=p.read_bytes(), mime_type="image/png")
                     for p in paths[i:i + batch]]
            total += client().models.count_tokens(model=settings.gemini_model, contents=parts).total_tokens or 0
        return total
    except Exception as e:
        log.info("count_tokens failed for images: %s", e)
        return None


def modality_tokens(usage) -> tuple[int | None, int | None]:
    """(image_tokens, text_tokens) from usage_metadata.prompt_tokens_details, if reported."""
    img = txt = None
    for d in (getattr(usage, "prompt_tokens_details", None) or []):
        name = str(getattr(d.modality, "value", d.modality)).upper()
        if name == "IMAGE":
            img = (img or 0) + (d.token_count or 0)
        elif name == "TEXT":
            txt = (txt or 0) + (d.token_count or 0)
    return img, txt


def grounding_comparison(session) -> dict:
    """Session-level: tokens for the grounding images vs. the same content sent as raw text."""
    text = "\n\n".join(f"FILE: {t}\n{body}" for t, body in session.grounding_texts)
    text_tokens = count_text(text) if text else 0
    image_tokens = count_images([session.context_dir / i["name"] for i in session.images])
    out = {"grounding_text_tokens": text_tokens}
    if image_tokens is not None:
        out["grounding_image_tokens"] = image_tokens
        out["grounding_savings_pct"] = round((1 - image_tokens / text_tokens) * 100, 1) if text_tokens else None
    return out
