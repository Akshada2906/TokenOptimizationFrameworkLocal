"""Build ordered PixelPrompt + native-visual context from an expense-policy PDF."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pdfplumber
import pymupdf
from google.genai import types

from src.helpers.pixel_renderer import render_text_pages


def _clean_cell(value: Any) -> str:
    return " ".join(str(value or "").split()).replace("|", "\\|")


def _table_markdown(rows: list[list[Any]]) -> str:
    width = max((len(row) for row in rows), default=0)
    matrix = [[_clean_cell(cell) for cell in row] + [""] * (width - len(row)) for row in rows]
    columns = [column for column in range(width) if any(row[column] for row in matrix)]
    normalized = [[row[column] for column in columns] for row in matrix]
    header, *body = normalized
    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join("---" for _ in header) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _tables(page: Any) -> list[tuple[pymupdf.Rect, str]]:
    result: list[tuple[pymupdf.Rect, str]] = []
    for table in page.find_tables():
        rows = table.extract() or []
        width = max((len(row) for row in rows), default=0)
        populated = sum(bool(_clean_cell(cell)) for row in rows for cell in row)
        if len(rows) >= 2 and width >= 2 and populated >= 4:
            result.append((pymupdf.Rect(table.bbox), _table_markdown(rows)))
    return result


def _mostly_inside(rect: pymupdf.Rect, container: pymupdf.Rect) -> bool:
    if rect.is_empty:
        return container.x0 - 2 <= rect.x0 <= container.x1 + 2 and container.y0 - 2 <= rect.y0 <= container.y1 + 2
    return (rect & container).get_area() >= rect.get_area() * 0.85


def _visual_rects(page: pymupdf.Page, table_rects: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Find substantial raster/vector regions while rejecting table rules and decoration."""
    page_area = page.rect.get_area()

    def is_page_furniture(rect: pymupdf.Rect) -> bool:
        """Reject repeated headers, footers, page numbers and edge artwork."""
        ratio = max(rect.width / max(rect.height, 1), rect.height / max(rect.width, 1))
        at_top_or_bottom = rect.y0 < page.rect.height * 0.12 or rect.y1 > page.rect.height * 0.88
        if at_top_or_bottom and ratio > 5:
            return True
        in_side_margin = rect.x0 < page.rect.width * 0.08 or rect.x1 > page.rect.width * 0.92
        return in_side_margin and rect.height > page.rect.height * 0.35 and rect.width < page.rect.width * 0.45

    candidates: list[pymupdf.Rect] = []
    for drawing in page.get_drawings():
        rect = pymupdf.Rect(drawing["rect"])
        if (
            rect.y0 > 70
            and rect.width >= page.rect.width * 0.25
            and rect.get_area() >= page_area * 0.025
            and not is_page_furniture(rect)
            and not any(_mostly_inside(rect, table) for table in table_rects)
        ):
            candidates.append(rect)
    for info in page.get_image_info():
        rect = pymupdf.Rect(info["bbox"])
        if (
            rect.get_area() >= page_area * 0.01
            and not is_page_furniture(rect)
            and not any(_mostly_inside(rect, table) for table in table_rects)
        ):
            candidates.append(rect)

    # Large background rectangles normally enclose all smaller shapes in a diagram.
    candidates.sort(key=lambda rect: rect.get_area(), reverse=True)
    selected: list[pymupdf.Rect] = []
    for rect in candidates:
        if any(existing.contains(rect) or (existing & rect).get_area() >= rect.get_area() * 0.85 for existing in selected):
            continue
        selected.append(rect)
    return sorted(selected, key=lambda rect: (rect.y0, rect.x0))


def _text_blocks(
    page: pymupdf.Page,
    excluded: list[pymupdf.Rect],
) -> list[tuple[pymupdf.Rect, str]]:
    blocks: list[tuple[pymupdf.Rect, str]] = []
    for block in page.get_text("blocks", sort=True):
        if block[6] != 0:
            continue
        rect = pymupdf.Rect(block[:4])
        value = block[4].replace("\x1f", " ").strip()
        if not value or any(rect.intersects(region) for region in excluded):
            continue
        blocks.append((rect, value))
    return blocks


def build_hybrid_policy(pdf_path: Path, output_dir: Path) -> dict[str, Any]:
    """Create an ordered manifest for every page of *pdf_path*."""
    document = pymupdf.open(pdf_path)
    plumber_document = pdfplumber.open(pdf_path)
    page_count = document.page_count
    manifest: list[dict[str, Any]] = []
    extracted_characters = 0
    parsed_tables = 0
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        # Consecutive prose and extracted-table events are intentionally batched. A native
        # visual is a hard boundary, so its position remains unambiguous to the model.
        pending_context: list[str] = []
        pending_start_page: int | None = None
        pending_end_page: int | None = None
        batch_number = 0

        def append_context(page_number: int, text: str) -> None:
            nonlocal pending_start_page, pending_end_page
            if pending_end_page != page_number:
                pending_context.append(f"\n\n=== PDF page {page_number} ===")
            pending_context.append(text)
            pending_start_page = page_number if pending_start_page is None else pending_start_page
            pending_end_page = page_number

        def flush_context() -> None:
            nonlocal batch_number, pending_start_page, pending_end_page
            if not pending_context or pending_start_page is None or pending_end_page is None:
                return
            batch_number += 1
            paths = render_text_pages(
                "\n\n".join(pending_context),
                title=f"PDF pages {pending_start_page}-{pending_end_page} - ordered text and tables",
                out_dir=output_dir,
                prefix=f"batch_{batch_number:03d}_pages_{pending_start_page:03d}-{pending_end_page:03d}",
                content_type="prose",
                font_px=18,
                max_pages=100,
            )
            for part, path in enumerate(paths, 1):
                manifest.append({
                    "pdf_page": pending_start_page,
                    "source_pages": list(range(pending_start_page, pending_end_page + 1)),
                    "item": batch_number,
                    "part": part,
                    "type": "pixelprompt_text",
                    "bbox": None,
                    "image": str(path.resolve()),
                    "label": (
                        f"PDF pages {pending_start_page}-{pending_end_page}, ordered text and "
                        f"extracted tables, part {part}"
                    ),
                })
            pending_context.clear()
            pending_start_page = None
            pending_end_page = None

        for page_number in range(1, page_count + 1):
            page = document[page_number - 1]
            tables = _tables(plumber_document.pages[page_number - 1])
            table_rects = [rect for rect, _ in tables]
            visuals = _visual_rects(page, table_rects)
            events: list[tuple[float, float, str, Any]] = [
                (rect.y0, rect.x0, "text", (rect, value))
                for rect, value in _text_blocks(page, table_rects + visuals)
            ]
            events.extend((rect.y0, rect.x0, "table", (rect, value)) for rect, value in tables)
            events.extend((rect.y0, rect.x0, "visual", rect) for rect in visuals)
            events.sort(key=lambda event: (event[0], event[1]))

            item_number = 0

            for _, _, kind, value in events:
                if kind == "text":
                    _, text = value
                    extracted_characters += len(text)
                    append_context(page_number, text)
                    continue
                if kind == "table":
                    _, markdown = value
                    extracted_characters += len(markdown)
                    parsed_tables += 1
                    append_context(page_number, "[EXTRACTED TABLE]\n" + markdown)
                else:
                    flush_context()
                    item_number += 1
                    rect = value
                    path = output_dir / f"page_{page_number:03d}_item_{item_number:03d}_visual.png"
                    clip = pymupdf.Rect(
                        max(page.rect.x0, rect.x0 - 6), max(page.rect.y0, rect.y0 - 6),
                        min(page.rect.x1, rect.x1 + 6), min(page.rect.y1, rect.y1 + 6),
                    )
                    page.get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip, alpha=False).save(path)
                    manifest.append({
                        "pdf_page": page_number,
                        "source_pages": [page_number],
                        "item": item_number,
                        "part": 1,
                        "type": "original_visual",
                        "bbox": [round(value, 2) for value in clip],
                        "image": str(path.resolve()),
                        "label": f"PDF page {page_number}, original visual {item_number}",
                    })
        flush_context()
    finally:
        plumber_document.close()
        document.close()

    if not manifest:
        raise ValueError("No usable content could be extracted from the PDF.")
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return {
        "manifest": manifest,
        "manifest_path": manifest_path,
        "pages": page_count,
        "extracted_characters": extracted_characters,
        "text_images": sum(item["type"] == "pixelprompt_text" for item in manifest),
        "table_images": parsed_tables,
        "visual_images": sum(item["type"] == "original_visual" for item in manifest),
        "total_images": len(manifest),
    }


def content_from_manifest(manifest: list[dict[str, Any]]) -> list[types.Content]:
    """Build Gemini multimodal content in the manifest's stable source order."""
    parts: list[types.Part] = [types.Part(text="Expense policy context in exact PDF reading order:")]
    for entry in manifest:
        parts.append(types.Part(text=entry["label"]))
        parts.append(types.Part.from_bytes(data=Path(entry["image"]).read_bytes(), mime_type="image/png"))
    return [
        types.Content(role="user", parts=parts),
        types.Content(role="model", parts=[types.Part(text="I will use this ordered policy context only.")]),
    ]
