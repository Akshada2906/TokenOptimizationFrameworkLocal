import shutil
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.config.settings import settings

STAGES = ["queued", "cloning", "analyzing", "rendering", "ready"]


@dataclass
class Session:
    id: str
    root: Path
    source: str = ""
    status: str = "queued"  # one of STAGES or "error"
    error: str | None = None
    created: float = field(default_factory=time.time)
    stats: dict[str, Any] = field(default_factory=dict)
    images: list[dict[str, Any]] = field(default_factory=list)  # grounding manifest
    history: list[dict[str, str]] = field(default_factory=list)
    local_repo: Path | None = None  # a folder analyzed in place (never deleted by cleanup)
    graph_dir: Path | None = None  # folder holding the code-review-graph (generated or pre-existing)
    graph_generated: bool = False  # True when we created it (so it can be saved into the user's folder)
    graph: Any = None
    omitted_files: list[str] = field(default_factory=list)  # code files over the image cap
    file_text_tokens: dict[str, int] = field(default_factory=dict)  # tokens of a file's text, cached
    file_image_tokens: dict[str, int] = field(default_factory=dict)  # exact image tokens of a unit, cached
    grounding_texts: list[tuple[str, str]] = field(default_factory=list)  # text behind each grounding image
    lock: threading.Lock = field(default_factory=threading.Lock)

    @property
    def repo_dir(self) -> Path:
        return self.local_repo or self.root / "repo"

    @property
    def context_dir(self) -> Path:
        return self.root / "context"


_sessions: dict[str, Session] = {}


def create_session(source: str) -> Session:
    cleanup_expired()
    sid = uuid.uuid4().hex[:12]
    root = settings.workspace_root / sid
    root.mkdir(parents=True)
    (root / "context").mkdir()
    session = Session(id=sid, root=root, source=source)
    _sessions[sid] = session
    return session


def get_session(sid: str) -> Session | None:
    return _sessions.get(sid)


def cleanup_expired() -> None:
    now = time.time()
    for sid, s in list(_sessions.items()):
        if now - s.created > settings.session_ttl_s:
            _sessions.pop(sid, None)
            shutil.rmtree(s.root, ignore_errors=True)
