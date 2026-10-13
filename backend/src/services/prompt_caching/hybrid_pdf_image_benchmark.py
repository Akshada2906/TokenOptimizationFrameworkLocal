r"""Standalone benchmark: PixelPrompt text plus original PDF figures in page order.

Example from backend (Command Prompt):
    set "PYTHONPATH=%CD%"
    ..\.venv\Scripts\python.exe -m src.services.prompt_caching.hybrid_pdf_image_benchmark ^
      --source-pdf "C:\path\to\document.pdf" --pages 206 207 --figure-page 206 ^
      --question "Where do the three outputs of Figure 6.8-1 go?"

Requires PyMuPDF, PixelPrompt, google-genai, and GEMINI_API_KEY in backend/.env.
Generated artifacts are under backend/artifacts/prompt_caching/hybrid_pdf_images/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pymupdf
import pdfplumber
from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.helpers.pixel_renderer import render_text_pages


BACKEND_DIR = Path(__file__).resolve().parents[3]
ARTIFACT_DIR = BACKEND_DIR / "artifacts" / "prompt_caching"
SYSTEM_INSTRUCTION = (
    "You are a document question-answering assistant. "
    "Answer only from the supplied document context and consider it in the provided order. "
    "Use all relevant text, tables, figures, and diagrams when forming the answer. "
    "If the document does not contain enough evidence, clearly say that the answer cannot be determined."
)


def _usage(response: Any) -> dict[str, int]:
    metadata = getattr(response, "usage_metadata", None)
    prompt = int(getattr(metadata, "prompt_token_count", 0) or 0)
    cached = int(getattr(metadata, "cached_content_token_count", 0) or 0)
    return {
        "prompt_tokens": prompt,
        "cached_tokens": cached,
        "new_input_tokens": max(prompt - cached, 0),
        "output_tokens": int(getattr(metadata, "candidates_token_count", 0) or 0),
    }


def _figure_rect(page: pymupdf.Page, manual: list[float] | None) -> pymupdf.Rect:
    if manual is not None:
        rect = pymupdf.Rect(manual)
        if rect.is_empty or not page.rect.contains(rect):
            raise ValueError(f"Figure crop {rect} is outside PDF page {page.number + 1}.")
        return rect

    # Image pieces can be adjacent strips, as Figure 6.8-1 is in the NASA PDF.
    candidates = [
        pymupdf.Rect(item["bbox"])
        for item in page.get_image_info()
        if pymupdf.Rect(item["bbox"]).width >= page.rect.width * 0.25
        and pymupdf.Rect(item["bbox"]).get_area() >= page.rect.get_area() * 0.03
    ]
    if not candidates:
        # A vector-only diagram has no embedded raster image: preserve the whole page.
        return page.rect
    rect = candidates[0]
    for item in candidates[1:]:
        rect |= item
    for block in page.get_text("blocks"):
        if block[6] != 0 or not re.search(r"\bfigure\s+\d", block[4], re.IGNORECASE):
            continue
        caption = pymupdf.Rect(block[:4])
        if 0 <= caption.y0 - rect.y1 <= 35:
            rect |= caption
    return pymupdf.Rect(
        max(page.rect.x0, rect.x0 - 8),
        max(page.rect.y0, rect.y0 - 8),
        min(page.rect.x1, rect.x1 + 8),
        min(page.rect.y1, rect.y1 + 8),
    )


def _text_blocks(
    page: pymupdf.Page,
    figure_rect: pymupdf.Rect | None,
    table_rects: list[pymupdf.Rect] | None = None,
) -> list[tuple[pymupdf.Rect, str]]:
    result = []
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:
            continue
        rect = pymupdf.Rect(block[:4])
        value = block[4].replace("\x1f", " ").strip()
        if not value or re.match(r"^NASA Systems Engineering Handbook\s+Rev", value):
            continue
        if figure_rect is not None and rect.intersects(figure_rect):
            continue  # Figure and caption are already visible in the original crop.
        if any(rect.intersects(table_rect) for table_rect in table_rects or []):
            continue  # Table text is emitted once as a structured Markdown table.
        result.append((rect, value))
    return result


def _has_visual_content(page: pymupdf.Page, table_rects: list[pymupdf.Rect]) -> bool:
    """Conservative page-level fallback for figures that cannot be safely cropped."""
    area = page.rect.get_area()
    image_area = sum(
        (pymupdf.Rect(info["bbox"]) & page.rect).get_area()
        for info in page.get_image_info()
    )
    expanded_tables = [pymupdf.Rect(rect.x0 - 2, rect.y0 - 2, rect.x1 + 2, rect.y1 + 2) for rect in table_rects]
    non_table_drawings = [
        drawing for drawing in page.get_drawings()
        if not any(table.contains(pymupdf.Rect(drawing["rect"])) for table in expanded_tables)
    ]
    return len(page.get_text("text").strip()) < 30 or image_area / area > 0.01 or len(non_table_drawings) > 10


def _clean_cell(value: Any) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _table_markdown(rows: list[list[Any]]) -> str:
    width = max((len(row) for row in rows), default=0)
    matrix = [[_clean_cell(cell) for cell in row] + [""] * (width - len(row)) for row in rows]
    populated_columns = [column for column in range(width) if any(row[column] for row in matrix)]
    normalized = [[row[column] for column in populated_columns] for row in matrix]
    header = normalized[0]
    body = normalized[1:]
    lines = ["| " + " | ".join(header) + " |", "| " + " | ".join("---" for _ in header) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _tables(page: Any) -> list[tuple[pymupdf.Rect, str]]:
    result: list[tuple[pymupdf.Rect, str]] = []
    for table in page.find_tables():
        rows = table.extract() or []
        width = max((len(row) for row in rows), default=0)
        populated = sum(bool(_clean_cell(cell)) for row in rows for cell in row)
        if len(rows) < 2 or width < 2 or populated < 4:
            continue
        result.append((pymupdf.Rect(table.bbox), _table_markdown(rows)))
    return result


def _build_manifest(
    pdf_path: Path,
    pages: list[int],
    figure_pages: set[int],
    output_dir: Path,
    manual_bbox: list[float] | None,
    auto_visual_pages: bool = False,
) -> list[dict[str, Any]]:
    document = pymupdf.open(pdf_path)
    plumber_document = pdfplumber.open(pdf_path)
    manifest: list[dict[str, Any]] = []
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        for page_number in pages:
            if not 1 <= page_number <= document.page_count:
                raise ValueError(f"Page {page_number} is outside this {document.page_count}-page PDF.")
            page = document[page_number - 1]
            tables = _tables(plumber_document.pages[page_number - 1])
            table_rects = [rect for rect, _ in tables]
            if auto_visual_pages and page_number not in figure_pages and _has_visual_content(page, table_rects):
                path = output_dir / f"page_{page_number:03d}_full.png"
                page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False).save(path)
                manifest.append({
                    "pdf_page": page_number, "item": 1, "type": "original_page",
                    "bbox": list(page.rect), "image": str(path),
                    "label": f"PDF page {page_number}, original full page (visual content)",
                })
                continue
            figure_rect = _figure_rect(page, manual_bbox) if page_number in figure_pages else None
            events: list[tuple[float, str, Any]] = [
                (rect.y0, "text", (rect, value)) for rect, value in _text_blocks(page, figure_rect, table_rects)
            ]
            events.extend((rect.y0, "table", (rect, value)) for rect, value in tables)
            if figure_rect is not None:
                events.append((figure_rect.y0, "figure", figure_rect))
            events.sort(key=lambda event: event[0])

            item_number = 0
            pending_text: list[str] = []
            pending_rect: pymupdf.Rect | None = None

            def flush_text() -> None:
                nonlocal item_number, pending_rect
                if not pending_text:
                    return
                item_number += 1
                prefix = f"page_{page_number:03d}_item_{item_number:03d}_text"
                paths = render_text_pages(
                    "\n\n".join(pending_text),
                    title=f"PDF page {page_number}, text item {item_number}",
                    out_dir=output_dir,
                    prefix=prefix,
                    content_type="prose",
                    font_px=20,
                    max_pages=1000,
                )
                for part_number, path in enumerate(paths, start=1):
                    manifest.append({
                        "pdf_page": page_number, "item": item_number, "part": part_number,
                        "type": "pixelprompt_text", "bbox": list(pending_rect), "image": str(path),
                        "label": f"PDF page {page_number}, text item {item_number}, part {part_number}",
                    })
                pending_text.clear()
                pending_rect = None

            for _, kind, value in events:
                if kind in {"figure", "table"}:
                    flush_text()
                    item_number += 1
                    if kind == "figure":
                        path = output_dir / f"page_{page_number:03d}_item_{item_number:03d}_figure.png"
                        page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=value, alpha=False).save(path)
                        manifest.append({
                            "pdf_page": page_number, "item": item_number, "type": "original_figure",
                            "bbox": list(value), "image": str(path),
                            "label": f"PDF page {page_number}, original figure and caption",
                        })
                    else:
                        table_rect, table_text = value
                        prefix = f"page_{page_number:03d}_item_{item_number:03d}_table"
                        paths = render_text_pages(
                            table_text,
                            title=f"PDF page {page_number}, extracted table {item_number}",
                            out_dir=output_dir,
                            prefix=prefix,
                            content_type="code",
                            font_px=16,
                            max_pages=1000,
                        )
                        for part_number, path in enumerate(paths, start=1):
                            manifest.append({
                                "pdf_page": page_number, "item": item_number, "part": part_number,
                                "type": "pixelprompt_table", "bbox": list(table_rect), "image": str(path),
                                "label": f"PDF page {page_number}, extracted table {item_number}, part {part_number}",
                            })
                else:
                    text_rect, text_value = value
                    pending_text.append(text_value)
                    pending_rect = text_rect if pending_rect is None else pending_rect | text_rect
            flush_text()
    finally:
        plumber_document.close()
        document.close()
    return manifest


def _content(manifest: list[dict[str, Any]]) -> types.Content:
    parts: list[types.Part] = [types.Part(text="PDF context in source-page order:")]
    for entry in manifest:
        parts.append(types.Part(text=entry["label"]))
        parts.append(types.Part.from_bytes(data=Path(entry["image"]).read_bytes(), mime_type="image/png"))
    return types.Content(role="user", parts=parts)


def _ask(client: genai.Client, model: str, question: str, context: types.Content | None, cache_name: str | None) -> dict[str, Any]:
    contents = ([context] if context is not None else []) + [
        types.Content(role="user", parts=[types.Part(text=question)])
    ]
    started = time.perf_counter()
    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            temperature=0,
            system_instruction=None if cache_name else SYSTEM_INSTRUCTION,
            cached_content=cache_name,
        ),
    )
    return {"answer": response.text or "", "latency_s": round(time.perf_counter() - started, 3), **_usage(response)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pdf", type=Path, required=True)
    page_selection = parser.add_mutually_exclusive_group(required=True)
    page_selection.add_argument("--pages", type=int, nargs="+", help="PDF page numbers, starting at 1.")
    page_selection.add_argument("--page-range", type=int, nargs=2, metavar=("FIRST", "LAST"), help="Inclusive PDF page range.")
    parser.add_argument("--figure-page", type=int, action="append", default=[], help="Page containing a figure to crop; may be repeated.")
    parser.add_argument("--auto-visual-pages", action="store_true", help="Use original full-page images for automatically detected visual pages.")
    parser.add_argument("--precheck-only", action="store_true", help="Generate images and count tokens without generating an answer or creating a cache.")
    parser.add_argument("--figure-bbox", type=float, nargs=4, metavar=("X0", "Y0", "X1", "Y1"), help="Optional crop for a single figure page, in PDF points.")
    parser.add_argument("--question", required=True)
    parser.add_argument("--ttl-seconds", type=int, default=3600)
    args = parser.parse_args()
    pdf_path = args.source_pdf.resolve()
    if not pdf_path.is_file():
        parser.error(f"PDF not found: {pdf_path}")
    if args.page_range:
        first, last = args.page_range
        if first < 1 or last < first:
            parser.error("--page-range must have FIRST >= 1 and LAST >= FIRST.")
        pages = list(range(first, last + 1))
    else:
        pages = sorted(set(args.pages))
    figure_pages = set(args.figure_page)
    if not figure_pages <= set(pages):
        parser.error("Every --figure-page must also be listed in --pages.")
    if not figure_pages and not args.auto_visual_pages:
        parser.error("Specify --figure-page or --auto-visual-pages.")
    if args.figure_bbox and len(figure_pages) != 1:
        parser.error("--figure-bbox requires exactly one --figure-page.")
    load_dotenv(BACKEND_DIR / ".env")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        parser.error("GEMINI_API_KEY is missing from backend/.env.")
    model = os.getenv("EXPENSE_CACHE_MODEL") or os.getenv("GEMINI_MODEL") or "gemini-2.5-flash"
    digest = hashlib.sha256(pdf_path.read_bytes()).hexdigest()[:12]
    output_dir = ARTIFACT_DIR / "hybrid_pdf_images" / f"{digest}_pages_{pages[0]}-{pages[-1]}_{len(pages)}"
    started = time.perf_counter()
    manifest = _build_manifest(pdf_path, pages, figure_pages, output_dir, args.figure_bbox, args.auto_visual_pages)
    if not manifest:
        raise RuntimeError("No text or figure images were generated.")
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    preparation_s = round(time.perf_counter() - started, 3)

    client = genai.Client(api_key=api_key)
    context = _content(manifest)
    counted = client.models.count_tokens(model=model, contents=[context])
    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "source_pdf": str(pdf_path),
        "pages": pages, "figure_pages": sorted(figure_pages), "manifest": str(manifest_path),
        "items": len(manifest), "pixelprompt_text_images": sum(item["type"] == "pixelprompt_text" for item in manifest),
        "pixelprompt_table_images": sum(item["type"] == "pixelprompt_table" for item in manifest),
        "original_figure_images": sum(item["type"] == "original_figure" for item in manifest),
        "original_page_images": sum(item["type"] == "original_page" for item in manifest),
        "preparation_s": preparation_s, "model": model, "question": args.question,
        "context_tokens": int(getattr(counted, "total_tokens", 0) or 0),
        "direct": None, "cached": None, "cache": {"status": "not_started"},
    }
    if args.precheck_only:
        output = ARTIFACT_DIR / f"hybrid_pdf_precheck_{datetime.now():%Y%m%d_%H%M%S}.json"
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(output), "items": report["items"], "context_tokens": report["context_tokens"], "manifest": report["manifest"]}, indent=2))
        return 0
    cache = None
    try:
        report["direct"] = _ask(client, model, args.question, context, None)
        created_at = time.perf_counter()
        cache = client.caches.create(
            model=model,
            config=types.CreateCachedContentConfig(
                contents=[context], system_instruction=SYSTEM_INSTRUCTION,
                ttl=f"{args.ttl_seconds}s",
            ),
        )
        report["cache"] = {"status": "created", "name": cache.name, "creation_s": round(time.perf_counter() - created_at, 3)}
        report["cached"] = _ask(client, model, args.question, None, cache.name)
        report["cache"]["status"] = "created_and_used" if report["cached"]["cached_tokens"] else "created_no_tokens_reported"
    except Exception as exc:
        report["cache"]["error"] = str(exc)
        report["cache"]["status"] = "failed"
    finally:
        if cache is not None:
            try:
                client.caches.delete(name=cache.name)
                report["cache"]["deleted_after_run"] = True
            except Exception as exc:
                report["cache"]["delete_error"] = str(exc)
        report["fresh_input_avoided"] = (
            report["direct"]["new_input_tokens"] - report["cached"]["new_input_tokens"]
            if report["direct"] and report["cached"] else None
        )
        output = ARTIFACT_DIR / f"hybrid_pdf_cache_{datetime.now():%Y%m%d_%H%M%S}.json"
        output.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps({"report": str(output), **report}, indent=2))
    return 0 if report["cached"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
