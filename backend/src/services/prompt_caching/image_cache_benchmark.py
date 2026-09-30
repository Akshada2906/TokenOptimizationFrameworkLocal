"""Compare cached and uncached Gemini requests over PixelPrompt policy images.

Run from ``backend``:
    uv run python -m src.services.prompt_caching.image_cache_benchmark --claims 3
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pypdf import PdfReader

from src.helpers.pixel_renderer import render_text_pages
from src.services.prompt_caching.policy_document import (
    extract_policy_pdf,
    generate_expense_policy_pdf,
)


BACKEND_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = Path(__file__).with_name("data")
ARTIFACT_DIR = BACKEND_DIR / "artifacts" / "prompt_caching"

SYSTEM_INSTRUCTION = """You are a financial-policy claim reviewer. Read the policy from
the supplied PixelPrompt images and use only that policy and the claim facts. Classify
the claim as Compliant, Non-compliant, or Needs review. Return JSON with exactly these
keys: classification, explanation, and policy_references."""


def _usage(response: Any) -> dict[str, int]:
    metadata = getattr(response, "usage_metadata", None)
    prompt_tokens = int(getattr(metadata, "prompt_token_count", 0) or 0)
    cached_tokens = int(getattr(metadata, "cached_content_token_count", 0) or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "new_input_tokens": max(prompt_tokens - cached_tokens, 0),
        "output_tokens": int(getattr(metadata, "candidates_token_count", 0) or 0),
        "total_tokens": int(getattr(metadata, "total_token_count", 0) or 0),
    }


def _classification(text: str) -> str | None:
    try:
        value = json.loads(text).get("classification")
    except (json.JSONDecodeError, AttributeError):
        return None
    return value if value in {"Compliant", "Non-compliant", "Needs review"} else None


def _image_parts(paths: list[Path]) -> list[types.Part]:
    return [types.Part.from_bytes(data=path.read_bytes(), mime_type="image/png") for path in paths]


def _policy_image_content(paths: list[Path]) -> types.Content:
    return types.Content(
        role="user",
        parts=[types.Part(text="Financial policy rendered as ordered PixelPrompt pages:")] + _image_parts(paths),
    )


def _claim_content(claim: dict[str, str]) -> types.Content:
    return types.Content(
        role="user",
        parts=[types.Part(text=f"Claim {claim['id']}:\n{claim['claim']}\n\nClassify this claim now.")],
    )


def _call(
    client: genai.Client,
    model: str,
    claim: dict[str, str],
    contents: list[types.Content],
    cached_content: str | None = None,
) -> dict[str, Any]:
    config = types.GenerateContentConfig(
        temperature=0,
        response_mime_type="application/json",
        cached_content=cached_content,
        system_instruction=None if cached_content else SYSTEM_INSTRUCTION,
    )
    started = time.perf_counter()
    response = client.models.generate_content(model=model, contents=contents, config=config)
    latency = time.perf_counter() - started
    text = response.text or ""
    classification = _classification(text)
    result = {
        "claim_id": claim["id"],
        "expected": claim["expected"],
        "classification": classification,
        "classification_matches_expected": classification == claim["expected"],
        "response": text,
        "latency_s": round(latency, 3),
    }
    result.update(_usage(response))
    return result


def _totals(rows: list[dict[str, Any]]) -> dict[str, int | float]:
    token_keys = ("prompt_tokens", "cached_tokens", "new_input_tokens", "output_tokens", "total_tokens")
    totals: dict[str, int | float] = {key: sum(int(row[key]) for row in rows) for key in token_keys}
    totals["latency_s"] = round(sum(float(row["latency_s"]) for row in rows), 3)
    totals["correct_classifications"] = sum(bool(row["classification_matches_expected"]) for row in rows)
    return totals


def _render_policy_images(pdf_path: Path, regenerate: bool) -> tuple[list[Path], int, int]:
    """Render each source PDF page separately so PixelPrompt text stays readable."""
    policy_text, pdf_pages = extract_policy_pdf(pdf_path)
    fingerprint = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:12]
    output_dir = ARTIFACT_DIR / "pixelprompt_images" / f"{fingerprint}_pagewise"
    existing = sorted(output_dir.glob("page_*.png"))
    if existing and not regenerate:
        return existing, pdf_pages, len(policy_text)

    images: list[Path] = []
    reader = PdfReader(str(pdf_path))
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = (page.extract_text() or "").strip()
        if not page_text:
            continue
        images.extend(
            render_text_pages(
                page_text,
                title=f"{pdf_path.name} — source page {page_number} of {len(reader.pages)}",
                out_dir=output_dir,
                prefix=f"page_{page_number:02d}",
                content_type="prose",
                max_pages=10,
            )
        )
    if not images:
        raise RuntimeError("PixelPrompt did not render any policy images.")
    return images, pdf_pages, len(policy_text)


def _markdown(report: dict[str, Any]) -> str:
    direct = report.get("without_cache")
    cached = report.get("with_cache")
    lines = [
        "# PixelPrompt Image-Caching Benchmark",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Model: `{report['model']}`",
        f"- Source PDF pages: {report['source_document']['pages']}",
        f"- PixelPrompt images: {report['pixelprompt_images']['count']}",
        f"- Image-context token precheck: {report['image_context_token_precheck']}",
        f"- Cache: {report['cache']['status']}",
        "",
        "| Metric | Images sent each request | Explicit image cache |",
        "|---|---:|---:|",
    ]
    for label, key in (
        ("Prompt tokens", "prompt_tokens"),
        ("Cached tokens", "cached_tokens"),
        ("New input tokens", "new_input_tokens"),
        ("Output tokens", "output_tokens"),
        ("Latency (s)", "latency_s"),
        ("Expected classifications", "correct_classifications"),
    ):
        left = direct["totals"][key] if direct else "—"
        right = cached["totals"][key] if cached else "—"
        lines.append(f"| {label} | {left} | {right} |")
    if direct and cached:
        avoided = int(direct["totals"]["new_input_tokens"]) - int(cached["totals"]["new_input_tokens"])
        lines.extend(("", f"Fresh input avoided by explicit image caching: **{avoided:,} tokens**."))
    return "\n".join(lines) + "\n"


def main() -> int:
    load_dotenv(BACKEND_DIR / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=int, default=3)
    parser.add_argument("--ttl-seconds", type=int, default=int(os.getenv("EXPENSE_CACHE_TTL_SECONDS", "3600")))
    parser.add_argument("--source-pdf", type=Path)
    parser.add_argument("--regenerate-images", action="store_true")
    parser.add_argument("--keep-cache", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Render PNGs without calling Gemini.")
    args = parser.parse_args()

    generated_pdf = ARTIFACT_DIR / "source_data" / "expense_policy_fy2026.pdf"
    pdf_path = args.source_pdf.resolve() if args.source_pdf else generated_pdf
    if args.source_pdf and not pdf_path.is_file():
        raise SystemExit(f"Source PDF not found: {pdf_path}")
    if not args.source_pdf and not pdf_path.is_file():
        generate_expense_policy_pdf(pdf_path)

    image_paths, pdf_pages, extracted_characters = _render_policy_images(pdf_path, args.regenerate_images)
    print(f"Rendered {len(image_paths)} PixelPrompt image(s) in: {image_paths[0].parent}")
    if args.prepare_only:
        return 0

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set. Add a rotated key to backend/.env.")
    model = os.getenv("EXPENSE_CACHE_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    claims = json.loads((DATA_DIR / "sample_claims.json").read_text(encoding="utf-8"))[: args.claims]
    if not claims:
        raise SystemExit("No claims selected. Pass --claims with a positive number.")

    client = genai.Client(api_key=api_key)
    image_content = _policy_image_content(image_paths)
    precheck = client.models.count_tokens(model=model, contents=[image_content])
    image_context_tokens = int(getattr(precheck, "total_tokens", 0) or 0)
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "source_document": {
            "path": str(pdf_path),
            "pages": pdf_pages,
            "extractable_characters": extracted_characters,
        },
        "pixelprompt_images": {"count": len(image_paths), "paths": [str(path) for path in image_paths]},
        "image_context_token_precheck": image_context_tokens,
        "cache": {"status": "not_started", "ttl_seconds": args.ttl_seconds},
        "without_cache": None,
        "with_cache": None,
    }

    direct_rows = [
        _call(client, model, claim, [image_content, _claim_content(claim)]) for claim in claims
    ]
    report["without_cache"] = {"results": direct_rows, "totals": _totals(direct_rows)}

    cache = None
    try:
        started = time.perf_counter()
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                contents=[image_content],
                system_instruction=SYSTEM_INSTRUCTION,
                ttl=f"{args.ttl_seconds}s",
            ),
        )
        cache_usage = getattr(cache, "usage_metadata", None)
        report["cache"] = {
            "status": "created",
            "name": cache.name,
            "ttl_seconds": args.ttl_seconds,
            "context_tokens": int(getattr(cache_usage, "total_token_count", 0) or image_context_tokens),
            "creation_latency_s": round(time.perf_counter() - started, 3),
        }
        cached_rows = [
            _call(client, model, claim, [_claim_content(claim)], cached_content=cache.name)
            for claim in claims
        ]
        report["with_cache"] = {"results": cached_rows, "totals": _totals(cached_rows)}
        report["cache"]["status"] = (
            "created_and_used"
            if any(row["cached_tokens"] > 0 for row in cached_rows)
            else "created_no_cache_tokens_reported"
        )
    except Exception as exc:
        report["cache"] = {
            "status": "unavailable",
            "error": str(exc),
            "ttl_seconds": args.ttl_seconds,
            "context_tokens": image_context_tokens,
        }
    finally:
        if cache is not None and not args.keep_cache:
            try:
                client.caches.delete(name=cache.name)
                report["cache"]["deleted_after_run"] = True
            except Exception as exc:
                report["cache"]["delete_error"] = str(exc)

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = ARTIFACT_DIR / f"image_cache_{stamp}.json"
    markdown_path = ARTIFACT_DIR / f"image_cache_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(_markdown(report))
    print(f"Detailed reports: {json_path} and {markdown_path}")
    return 0 if report["with_cache"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
