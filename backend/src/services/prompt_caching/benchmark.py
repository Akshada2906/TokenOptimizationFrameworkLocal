"""Compare direct Gemini prompts with explicit caching for expense-policy checks.

Run from ``backend``:
    uv run python -m src.services.prompt_caching.benchmark
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.services.prompt_caching.policy_document import extract_policy_pdf, generate_expense_policy_pdf
from src.services.prompt_caching.reviewer import (
    SYSTEM_INSTRUCTION,
    create_structured_client,
    review_claim,
)


BACKEND_DIR = Path(__file__).resolve().parents[3]
DATA_DIR = Path(__file__).with_name("data")
REPORT_DIR = BACKEND_DIR / "artifacts" / "prompt_caching"

def _part(text: str) -> types.Part:
    return types.Part(text=text)


def _policy_contents(policy: str) -> list[types.Content]:
    return [
        types.Content(role="user", parts=[_part("Expense policy to apply:\n\n" + policy)]),
        types.Content(role="model", parts=[_part("I will apply this policy exactly to each claim.")]),
    ]


def _usage(response: Any) -> dict[str, int]:
    usage = getattr(response, "usage_metadata", None)
    prompt_tokens = int(getattr(usage, "prompt_token_count", 0) or 0)
    cached_tokens = int(getattr(usage, "cached_content_token_count", 0) or 0)
    return {
        "prompt_tokens": prompt_tokens,
        "cached_tokens": cached_tokens,
        "new_input_tokens": max(prompt_tokens - cached_tokens, 0),
        "output_tokens": int(getattr(usage, "candidates_token_count", 0) or 0),
        "total_tokens": int(getattr(usage, "total_token_count", 0) or 0),
    }


def _call(
    client: Any,
    model: str,
    claim: dict[str, str],
    policy_text: str | None = None,
    cached_content: str | None = None,
) -> dict[str, Any]:
    started = time.perf_counter()
    answer, response = review_claim(
        client,
        model,
        claim["claim"],
        claim_id=claim["id"],
        policy_text=policy_text,
        cached_content=cached_content,
    )
    elapsed_s = time.perf_counter() - started
    result = {
        "claim_id": claim["id"],
        "expected": claim["expected"],
        "classification": answer.classification,
        "classification_matches_expected": answer.classification == claim["expected"],
        "response": answer.model_dump(),
        "latency_s": round(elapsed_s, 3),
    }
    result.update(_usage(response))
    return result


def _totals(results: list[dict[str, Any]]) -> dict[str, int | float]:
    keys = ("prompt_tokens", "cached_tokens", "new_input_tokens", "output_tokens", "total_tokens")
    total: dict[str, int | float] = {key: sum(int(row[key]) for row in results) for key in keys}
    total["latency_s"] = round(sum(float(row["latency_s"]) for row in results), 3)
    total["correct_classifications"] = sum(bool(row["classification_matches_expected"]) for row in results)
    return total


def _markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Expense Policy Prompt-Caching POC Report",
        "",
        f"- Generated: {report['generated_at']}",
        f"- Model: `{report['model']}`",
        f"- Claims: {report['claims_run']}",
        f"- Source document: `{report['source_document']['path']}` ({report['source_document']['pages']} pages)",
        f"- Policy token precheck: {report['policy_token_precheck']}",
        f"- Cache: {report['cache']['status']}",
        "",
        "| Metric | Without explicit cache | With explicit cache |",
        "|---|---:|---:|",
    ]
    direct, cached = report.get("without_cache"), report.get("with_cache")
    for label, key in (("Prompt tokens", "prompt_tokens"), ("Cached tokens", "cached_tokens"),
                       ("New input tokens", "new_input_tokens"), ("Output tokens", "output_tokens"),
                       ("Latency (s)", "latency_s"), ("Expected classifications", "correct_classifications")):
        lines.append(f"| {label} | {direct['totals'][key] if direct else '—'} | {cached['totals'][key] if cached else '—'} |")
    if cached and direct:
        implicit = int(direct["totals"]["cached_tokens"])
        additional_saved = int(direct["totals"]["new_input_tokens"]) - int(cached["totals"]["new_input_tokens"])
        reduction = additional_saved / int(direct["totals"]["new_input_tokens"]) * 100 if direct["totals"]["new_input_tokens"] else 0
        lines.extend((
            "",
            f"Gemini reported **{implicit:,} implicitly cached tokens** in the no-explicit-cache baseline.",
            f"Explicit caching reduced remaining fresh input by **{additional_saved:,} tokens** ({reduction:.1f}%) compared with that baseline.",
        ))
    return "\n".join(lines) + "\n"


def main() -> int:
    load_dotenv(BACKEND_DIR / ".env")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claims", type=int, default=12, help="Number of sample claims to run (default: all 12).")
    parser.add_argument("--ttl-seconds", type=int, default=int(os.getenv("EXPENSE_CACHE_TTL_SECONDS", "3600")))
    parser.add_argument("--keep-cache", action="store_true", help="Do not delete the Gemini cache after the benchmark.")
    parser.add_argument("--source-pdf", type=Path, help="Use an existing selectable-text policy PDF instead of the generated source document.")
    parser.add_argument("--regenerate-pdf", action="store_true", help="Rebuild the generated 19-page expense-policy PDF before the run.")
    args = parser.parse_args()

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is not set. Add it to backend/.env before running this POC.")
    model = os.getenv("EXPENSE_CACHE_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    claims = json.loads((DATA_DIR / "sample_claims.json").read_text(encoding="utf-8"))[:args.claims]
    if not claims:
        raise SystemExit("No claims selected. Pass --claims with a positive number.")

    generated_pdf = BACKEND_DIR / "artifacts" / "prompt_caching" / "source_data" / "expense_policy_fy2026.pdf"
    pdf_path = args.source_pdf.resolve() if args.source_pdf else generated_pdf
    if args.source_pdf and not pdf_path.is_file():
        raise SystemExit(f"Source PDF not found: {pdf_path}")
    if not args.source_pdf and (args.regenerate_pdf or not pdf_path.is_file()):
        generate_expense_policy_pdf(pdf_path)
    policy, pdf_pages = extract_policy_pdf(pdf_path)
    stable_contents = _policy_contents(policy)
    client = genai.Client(api_key=api_key)
    try:
        precheck = client.models.count_tokens(model=model, contents=stable_contents)
        policy_tokens: int | str = int(getattr(precheck, "total_tokens", 0) or 0)
    except Exception as exc:
        policy_tokens = f"unavailable ({exc})"

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "claims_run": len(claims),
        "source_document": {"path": str(pdf_path), "pages": pdf_pages, "extractable_characters": len(policy)},
        "policy_characters": len(policy),
        "policy_token_precheck": policy_tokens,
        "cache": {"status": "not_started", "ttl_seconds": args.ttl_seconds},
        "without_cache": None,
        "with_cache": None,
    }
    structured_client = create_structured_client(client)
    direct_results = [_call(structured_client, model, claim, policy_text=policy) for claim in claims]
    report["without_cache"] = {"results": direct_results, "totals": _totals(direct_results)}

    cache = None
    cached_results: list[dict[str, Any]] = []
    cache_context_tokens = int(policy_tokens) if isinstance(policy_tokens, int) else 0
    cache_started = time.perf_counter()
    try:
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                contents=stable_contents, system_instruction=SYSTEM_INSTRUCTION, ttl=f"{args.ttl_seconds}s"
            ),
        )
        cache_usage = getattr(cache, "usage_metadata", None)
        cache_context_tokens = int(getattr(cache_usage, "total_token_count", 0) or cache_context_tokens)
        report["cache"] = {
            "status": "created",
            "name": cache.name,
            "ttl_seconds": args.ttl_seconds,
            "context_tokens": cache_context_tokens,
            "creation_latency_s": round(time.perf_counter() - cache_started, 3),
        }
        cached_results = [_call(structured_client, model, claim, [], cached_content=cache.name) for claim in claims]
        report["with_cache"] = {"results": cached_results, "totals": _totals(cached_results)}
        report["cache"]["status"] = "created_and_used" if any(row["cached_tokens"] > 0 for row in cached_results) else "created_no_cache_tokens_reported"
    except Exception as exc:
        report["cache"] = {
            "status": "unavailable",
            "error": str(exc),
            "ttl_seconds": args.ttl_seconds,
            "context_tokens": cache_context_tokens,
        }
    finally:
        if cache is not None and not args.keep_cache:
            try:
                client.caches.delete(name=cache.name)
                report["cache"]["deleted_after_run"] = True
            except Exception as exc:
                report["cache"]["delete_error"] = str(exc)

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = REPORT_DIR / f"expense_cache_{stamp}.json"
    markdown_path = REPORT_DIR / f"expense_cache_{stamp}.md"
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown(report), encoding="utf-8")
    print(_markdown(report))
    print(f"Detailed reports: {json_path} and {markdown_path}")
    return 0 if report["with_cache"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
