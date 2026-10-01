"""Code file indexing: every code file in the repo is a candidate the assistant can ask for.

Files are not rendered to images here. Ingestion only builds the list of candidate paths;
`context_router.select()` matches a question against that full list, and `chat.answer()` renders
just the selected file(s) to images on demand (see `render_selected_files` in chat.py). This keeps
ingestion cheap regardless of repo size and never hides a file from the assistant.
"""
from pathlib import Path

from src.config.settings import settings
from src.services.pixelprompt.workspace import IGNORED_DIRS, is_code_file, iter_repo_files

DOC_EXTS = {".md", ".mdx"}  # docs are already rendered as grounding pages
DATA_EXTS = {".json", ".xml"}  # often data stores; only small ones are treated as code/config


def index_code_files(repo: Path) -> list[str]:
    """Every code/config file in the repo, by path relative to it. No cap, nothing omitted."""
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
        out.append(rel)
    return out
