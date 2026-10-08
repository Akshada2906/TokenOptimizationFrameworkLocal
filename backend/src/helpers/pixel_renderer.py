"""Thin wrapper over the `pixelprompt` library: turns text/files into optimized PNG pages."""
import dataclasses
import math
from pathlib import Path

from PIL import Image
from pixelprompt import PixelPrompt, RenderConfig

from src.config.settings import settings

TILE = 768  # Gemini bills images per 768px tile (258 tokens each)


def estimate_image_tokens(width: int, height: int) -> int:
    """Gemini image cost estimate (exact numbers come back in usage_metadata)."""
    if width <= 384 and height <= 384:
        return 258
    return math.ceil(width / TILE) * math.ceil(height / TILE) * 258


def _renderer(content_type: str, font_px: int | None = None) -> PixelPrompt:
    cfg = RenderConfig.for_content(content_type)  # presets: prose | json | code | config
    cfg = dataclasses.replace(cfg, max_width=settings.pixel_page_px, max_height=settings.pixel_page_px)
    font_px = font_px or settings.pixel_font_px
    if font_px:
        cfg = dataclasses.replace(cfg, font_size=font_px)
    return PixelPrompt(cfg)


def render_text_pages(
    text: str,
    title: str,
    out_dir: Path,
    prefix: str,
    content_type: str = "prose",
    max_pages: int = 4,
    numbered: bool = False,
    font_px: int | None = None,
) -> list[Path]:
    """Render text to PNG pages with PixelPrompt; returns saved paths (at most max_pages)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    if numbered:
        width = len(str(len(text.splitlines()) or 1))
        text = "\n".join(f"{i:>{width}} {ln}" for i, ln in enumerate(text.splitlines(), start=1))
    body = f"FILE: {title}\n{text}" if text.strip() else f"FILE: {title}\n(empty)"
    images = _renderer(content_type, font_px).render(body)
    paths: list[Path] = []
    for idx, img in enumerate(images[:max_pages], start=1):
        path = out_dir / f"{prefix}_{idx:02d}.png"
        img.save(str(path))
        paths.append(path)
    return paths


def fit_image(src: Path, dest: Path, max_px: int | None = None) -> Path:
    """Downscale an existing image (e.g. a diagram) so it fits the same page budget."""
    max_px = max_px or settings.pixel_page_px
    img = Image.open(src).convert("RGB")
    if max(img.size) > max_px:
        img.thumbnail((max_px, max_px))
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, optimize=True)
    return dest


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as im:
        return im.size
