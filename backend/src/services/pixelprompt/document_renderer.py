"""Render non-code repo files (images, PDFs, .docx) into the same PNG-page sequence the rest of
PixelPrompt sends to the LLM.

Plain images are passed through as-is. PDFs and .docx files are walked in document order: pages/
paragraphs that are pure text are batched and rendered into dense PixelPrompt pages, while a page
that contains a genuine diagram (not a tiny icon/bullet) is kept as a real image instead of being
flattened into text — PixelPrompt has no way to represent a diagram inside a block of rendered
text, so the only way to preserve it is to ship that page as an image in its original place in the
sequence. The returned list is therefore a mix of dense-text pages and raw diagram pages, in the
same order they appear in the source document.
"""
from pathlib import Path

import docx
import pymupdf
from docx.oxml.ns import qn

from src.config.settings import settings
from src.helpers.pixel_renderer import fit_image, render_text_pages

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff", ".webp"}
DOCX_IMAGE_MIME_EXT = {  # raster formats PIL can read; vector embeds (emf/wmf) are skipped
    "image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
    "image/bmp": ".bmp", "image/tiff": ".tiff",
}

MIN_DIAGRAM_AREA_PX = 120 * 120  # below this, treat an embedded image as an icon/bullet, not a diagram
PDF_TEXT_CHUNK_PAGES = 4  # how many consecutive text-only PDF pages go into one dense image batch
DOCX_TEXT_CHUNK_CHARS = 6000  # how much consecutive paragraph text goes into one dense image batch


def render_document_to_images(path: Path, out_dir: Path, prefix: str) -> list[Path]:
    """Dispatch by extension. Raises ValueError for anything not supported here."""
    suffix = path.suffix.lower()
    out_dir.mkdir(parents=True, exist_ok=True)
    if suffix == ".pdf":
        return _render_pdf(path, out_dir, prefix)
    if suffix == ".docx":
        return _render_docx(path, out_dir, prefix)
    if suffix in IMAGE_EXTS:
        return [fit_image(path, out_dir / f"{prefix}_image.png")]
    raise ValueError(f"Unsupported document type: {suffix}")


# --- PDF ---------------------------------------------------------------------

def _pdf_page_has_diagram(page: "pymupdf.Page") -> bool:
    return any(w * h >= MIN_DIAGRAM_AREA_PX for _xref, _smask, w, h, *_ in page.get_images(full=True))


def _rasterize_pdf_page(page: "pymupdf.Page", dest: Path, max_px: int) -> Path:
    zoom = min(max_px / max(page.rect.width, page.rect.height, 1), 3.0)
    page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom)).save(str(dest))
    return dest


def _render_pdf(pdf_path: Path, out_dir: Path, prefix: str) -> list[Path]:
    doc = pymupdf.open(str(pdf_path))
    try:
        image_paths: list[Path] = []
        seq = 0
        buffer: list[str] = []

        def flush_text():
            nonlocal buffer, seq
            if not buffer:
                return
            seq += 1
            image_paths.extend(render_text_pages(
                "\n\n".join(buffer), pdf_path.name, out_dir, f"{prefix}_{seq:04d}_text",
                content_type="prose", max_pages=PDF_TEXT_CHUNK_PAGES))
            buffer = []

        for i, page in enumerate(doc, start=1):
            if _pdf_page_has_diagram(page):
                flush_text()
                seq += 1
                dest = out_dir / f"{prefix}_{seq:04d}_page{i:04d}.png"
                image_paths.append(_rasterize_pdf_page(page, dest, settings.pixel_page_px))
                continue
            buffer.append(f"--- page {i} ---\n{(page.get_text() or '').strip() or '(no extractable text)'}")
            if len(buffer) >= PDF_TEXT_CHUNK_PAGES:
                flush_text()
        flush_text()
        return image_paths
    finally:
        doc.close()


# --- DOCX ----------------------------------------------------------------------

def _render_docx(docx_path: Path, out_dir: Path, prefix: str) -> list[Path]:
    document = docx.Document(str(docx_path))
    image_paths: list[Path] = []
    seq = 0
    buffer: list[str] = []
    buffer_len = 0

    def flush_text():
        nonlocal buffer, buffer_len, seq
        if not buffer:
            return
        seq += 1
        image_paths.extend(render_text_pages(
            "\n".join(buffer), docx_path.name, out_dir, f"{prefix}_{seq:04d}_text",
            content_type="prose", max_pages=4))
        buffer, buffer_len = [], 0

    for para in document.paragraphs:
        blips = para._element.findall(".//" + qn("a:blip"))
        if blips:
            flush_text()
            for blip in blips:
                rid = blip.get(qn("r:embed"))
                part = document.part.related_parts.get(rid) if rid else None
                ext = DOCX_IMAGE_MIME_EXT.get(part.content_type) if part else None
                if not part or not ext:
                    continue  # unsupported embed (e.g. vector emf/wmf) -- skip rather than fail the page
                seq += 1
                raw = out_dir / f"{prefix}_{seq:04d}_img{ext}"
                raw.write_bytes(part.blob)
                image_paths.append(fit_image(raw, out_dir / f"{prefix}_{seq:04d}_img.png"))
        text = para.text.strip()
        if text:
            buffer.append(text)
            buffer_len += len(text)
            if buffer_len >= DOCX_TEXT_CHUNK_CHARS:
                flush_text()
    flush_text()
    return image_paths
