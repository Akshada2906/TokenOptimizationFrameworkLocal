from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile

from src.config.settings import settings
from src.schemas.api import (ChatRequest, ChatResponse, CreateSessionRequest, FileContent,
                             LocalFolderRequest, SessionCreated, SessionStatus)
from src.services.pixelprompt import chat as chat_service
from src.services.pixelprompt.pipeline import run_pipeline
from src.services.pixelprompt.session_store import Session, create_session, get_session
from src.services.pixelprompt.workspace import (GITIGNORE_BLOCK, GRAPH_DIR, WorkspaceError, build_tree, safe_repo_path,
                                    save_upload, validate_local_path, validate_repo_url)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


def _session(sid: str) -> Session:
    s = get_session(sid)
    if not s:
        raise HTTPException(404, "Session not found or expired.")
    return s


def _ready(sid: str) -> Session:
    s = _session(sid)
    if s.status != "ready":
        raise HTTPException(409, f"Session not ready (status: {s.status}).")
    return s


@router.post("", response_model=SessionCreated)
def create_from_url(body: CreateSessionRequest, tasks: BackgroundTasks):
    try:
        url = validate_repo_url(body.repo_url)
    except WorkspaceError as e:
        raise HTTPException(400, str(e))
    session = create_session(url)
    tasks.add_task(run_pipeline, session, url)
    return SessionCreated(session_id=session.id)


@router.post("/local", response_model=SessionCreated)
def create_from_local(body: LocalFolderRequest, tasks: BackgroundTasks):
    """Analyze a folder on this machine in place; code-review-graph/ is written inside it."""
    if not settings.allow_local_paths:
        raise HTTPException(403, "Local folder analysis is disabled on this server.")
    try:
        path = validate_local_path(body.path)
    except WorkspaceError as e:
        raise HTTPException(400, str(e))
    session = create_session(str(path))
    session.local_repo = path
    tasks.add_task(run_pipeline, session, None)
    return SessionCreated(session_id=session.id)


@router.post("/upload", response_model=SessionCreated)
async def create_from_upload(request: Request, tasks: BackgroundTasks):
    # Parse the form ourselves: Starlette defaults to max 1000 files per request.
    limit = settings.max_repo_files
    session = create_session("upload")
    try:
        async with request.form(max_files=limit + 1, max_fields=limit + 1) as form:
            uploads = [f for f in form.getlist("files") if isinstance(f, UploadFile)]
            if not uploads:
                raise WorkspaceError("No files received.")
            payload = [(f.filename or "", await f.read()) for f in uploads]
        save_upload(payload, session.repo_dir)
    except WorkspaceError as e:
        session.status, session.error = "error", str(e)
        raise HTTPException(400, str(e))
    tasks.add_task(run_pipeline, session, None)
    return SessionCreated(session_id=session.id)


@router.get("/{sid}", response_model=SessionStatus)
def status(sid: str):
    s = _session(sid)
    return SessionStatus(session_id=s.id, status=s.status, error=s.error, source=s.source, stats=s.stats)


@router.get("/{sid}/tree")
def tree(sid: str):
    s = _session(sid)
    if not s.repo_dir.exists():
        raise HTTPException(409, "Repository not available yet.")
    return build_tree(s.repo_dir)


@router.get("/{sid}/file", response_model=FileContent)
def read_file(sid: str, path: str):
    s = _session(sid)
    try:
        target = safe_repo_path(s.repo_dir, path)
    except WorkspaceError as e:
        raise HTTPException(400, str(e))
    if not target.is_file():
        raise HTTPException(404, "File not found.")
    if target.stat().st_size > settings.max_file_view_bytes:
        raise HTTPException(413, "File too large to display.")
    try:
        return FileContent(path=path, content=target.read_text(encoding="utf-8"))
    except UnicodeDecodeError:
        raise HTTPException(415, "Binary file.")


@router.get("/{sid}/context")
def context(sid: str):
    s = _ready(sid)
    return {"images": s.images, "stats": s.stats}


@router.get("/{sid}/context/image")
def context_image(sid: str, name: str):
    s = _ready(sid)
    target = (s.context_dir / name).resolve()
    if s.context_dir.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "Not found.")
    return FileResponse(target)


def _graph_files(s: Session) -> list[dict]:
    files = []
    if s.graph_dir and s.graph_dir.is_dir():
        for p in sorted(s.graph_dir.rglob("*")):
            rel = p.relative_to(s.graph_dir)
            if p.is_file() and "cache" not in rel.parts and not p.name.startswith("."):
                files.append({"path": rel.as_posix(), "size": p.stat().st_size})
    return files


@router.get("/{sid}/graph-files")
def graph_files(sid: str):
    """Files of a graph WE generated, so the browser can save them into the user's own folder."""
    s = _ready(sid)
    files = _graph_files(s) if s.graph_generated else []
    return {"folder": GRAPH_DIR, "files": files, "gitignore": GITIGNORE_BLOCK}


@router.get("/{sid}/graph")
def graph_info(sid: str):
    """Everything the UI needs to show the knowledge graph and the folder/files behind it."""
    s = _ready(sid)
    files = _graph_files(s)
    return {
        "folder": s.graph_dir.name if s.graph_dir else GRAPH_DIR,
        "path": str(s.graph_dir) if s.graph_dir else None,
        "generated": s.graph_generated,
        "source": s.stats.get("graph_source"),
        "nodes": s.stats.get("graph_nodes", 0),
        "edges": s.stats.get("graph_edges", 0),
        "has_html": any(f["path"] == "graph.html" for f in files),
        "files": files,
    }


@router.get("/{sid}/graph-file")
def graph_file(sid: str, path: str):
    s = _ready(sid)
    if not s.graph_dir:
        raise HTTPException(404, "No graph for this session.")
    target = (s.graph_dir / path).resolve()
    if s.graph_dir.resolve() not in target.parents or not target.is_file():
        raise HTTPException(404, "Not found.")
    return FileResponse(target)


@router.get("/{sid}/graph.html")
def graph_html(sid: str):
    s = _ready(sid)
    html = s.graph_dir / "graph.html" if s.graph_dir else None
    if not html or not html.is_file():
        raise HTTPException(404, "No interactive graph for this repository.")
    return FileResponse(html, media_type="text/html")


@router.get("/{sid}/diagram.svg")
def diagram_svg(sid: str):
    s = _ready(sid)
    svg = s.context_dir / "diagrams" / "dependencies.svg"
    if not svg.exists():
        raise HTTPException(404, "No diagram for this repository.")
    return FileResponse(svg, media_type="image/svg+xml")


@router.post("/{sid}/chat", response_model=ChatResponse)
def chat(sid: str, body: ChatRequest):
    s = _ready(sid)
    with s.lock:
        try:
            return ChatResponse(**chat_service.answer(s, body.message, body.open_file))
        except chat_service.ChatError as e:
            raise HTTPException(502, str(e))


@router.get("/{sid}/history")
def history(sid: str):
    return _session(sid).history
