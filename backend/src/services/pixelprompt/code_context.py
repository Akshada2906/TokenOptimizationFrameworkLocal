"""File indexing: every file in the repo is a candidate the assistant can ask for.

Files are not rendered to images here. Ingestion only builds the list of candidate paths;
`context_router.select()` matches a question against that full list, and `chat.answer()` renders
just the selected file(s) to images on demand (see `render_selected_files` in chat.py). This keeps
ingestion cheap regardless of repo size and never hides a file from the assistant.
"""
from pathlib import Path

from src.services.pixelprompt.workspace import IGNORED_DIRS, iter_repo_files


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



