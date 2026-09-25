from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import FileResponse
from starlette.datastructures import UploadFile

from src.config.settings import settings
from src.schemas.api import (ChatRequest, ChatResponse, CreateSessionRequest, FileContent,
                             SessionCreated, SessionStatus)
from src.services import chat as chat_service
from src.services.pipeline import run_pipeline
from src.services.session_store import Session, create_session, get_session
from src.services.workspace import WorkspaceError, build_tree, safe_repo_path, save_upload, validate_repo_url

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
