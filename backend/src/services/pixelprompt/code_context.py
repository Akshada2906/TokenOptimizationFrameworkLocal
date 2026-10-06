"""Per-file code images: every code file in the repo is rendered to its own PixelPrompt image(s)."""
from collections import defaultdict
from pathlib import Path

from src.config.settings import settings
from src.helpers.pixel_renderer import render_text_pages
from src.services.pixelprompt.graph import Graph
from src.services.pixelprompt.workspace import IGNORED_DIRS, is_code_file, iter_repo_files

DOC_EXTS = {".md", ".mdx"}  # docs are already rendered as grounding pages
DATA_EXTS = {".json", ".xml"}  # often data stores; only small ones are treated as code/config


def _candidates(repo: Path) -> list[tuple[str, str]]:
    out = []
    for p in iter_repo_files(repo):
        rel = str(p.relative_to(repo))
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if not size or size > settings.max_code_file_bytes or not is_code_file(rel, size):
            continue
        if p.suffix.lower() in DOC_EXTS or (p.suffix.lower() in DATA_EXTS and size > 30_000):
            continue
        if any(part in IGNORED_DIRS for part in p.relative_to(repo).parts):
            continue
        try:
            out.append((rel, p.read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return out


def _importance(graph: Graph | None) -> dict[str, int]:
    """Graph degree per file: more connected files are rendered first (matters when a cap applies)."""
    score: dict[str, int] = defaultdict(int)
    if graph:
        for nid, d in graph.degree().items():
            f = graph.nodes.get(nid, {}).get("file")
            if f:
                score[f] += d
    return score


def render_code_images(repo: Path, graph: Graph | None, out_dir: Path):
    """Returns (entries, texts, included, omitted).

    entries: one dict per image {path, title, file, page, pages}; texts: (path, source) for the
    text-vs-image comparison; included/omitted: file paths.
    """
    files = _candidates(repo)
    score = _importance(graph)

    def key(item):
        rel, text = item
        best = max((v for f, v in score.items() if f == rel or rel.endswith("/" + f)), default=0)
        return (-best, len(text))

    files.sort(key=key)
    entries, texts, included, omitted = [], [], [], []
    out_dir.mkdir(parents=True, exist_ok=True)
    for i, (rel, text) in enumerate(files):
        if len(entries) >= settings.max_code_images:
            omitted.append(rel)
            continue
        pages = render_text_pages(text, rel, out_dir, f"{i:04d}", "code", settings.max_file_pages,
                                  numbered=True, font_px=settings.pixel_code_font_px)
        for n, p in enumerate(pages, start=1):
            entries.append({"path": p, "title": rel, "file": rel, "page": n, "pages": len(pages)})
        texts.append((rel, text))
        included.append(rel)
    return entries, texts, included, omitted


def index_code_files(repo: Path) -> list[str]:
    """Every file in the repo (outside ignored/vendored dirs), by path relative to it."""
    out = []
    for p in iter_repo_files(repo):
        rel = str(p.relative_to(repo))
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if not size:
            continue
        if any(part in IGNORED_DIRS for part in p.relative_to(repo).parts):
            continue
        out.append(rel)
    return out
