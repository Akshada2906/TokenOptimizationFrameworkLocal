import hashlib
import time
import logging

from google import genai
from google.genai import types

from src.config.settings import settings
from src.helpers.pixel_renderer import estimate_image_tokens, image_size, render_text_pages
from src.prompts import prompt
from src.services.pixelprompt.context_router import select
from src.services.pixelprompt.graph import graph_slice
from src.services.pixelprompt.session_store import Session
from src.services.pixelprompt.tokens import count_images, count_text, modality_tokens
from src.services.pixelprompt.workspace import WorkspaceError, safe_repo_path

log = logging.getLogger(__name__)
_client: genai.Client | None = None
HISTORY_TURNS = 10


class ChatError(Exception):
    pass


def client() -> genai.Client:
    global _client
    if not settings.gemini_api_key:
        raise ChatError("GEMINI_API_KEY is not configured on the server.")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _image_part(path) -> types.Part:
    return types.Part.from_bytes(data=path.read_bytes(), mime_type="image/png")


def render_open_file(session: Session, rel: str):
    """Render just the open file on demand (cached per path+mtime). Returns (paths, text)."""
    try:
        target = safe_repo_path(session.repo_dir, rel)
    except WorkspaceError as e:
        raise ChatError(str(e))
    if not target.is_file():
        raise ChatError(f"File not found: {rel}")
    try:
        text = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ChatError("Binary files can't be sent to the assistant.")
    key = hashlib.sha1(f"{rel}:{target.stat().st_mtime_ns}".encode()).hexdigest()[:12]
    out_dir = session.context_dir / "files"
    existing = sorted(out_dir.glob(f"{key}_*.png")) if out_dir.exists() else []
    if not existing:
        existing = render_text_pages(text, rel, out_dir, key, "code", settings.max_file_pages,
                                     numbered=True, font_px=settings.pixel_file_font_px)
    return existing


def _generate_with_retry(contents, config, attempts: int = 4):
    """Retry brief Gemini capacity spikes (503/429) with backoff."""
    for i in range(attempts):
        try:
            return client().models.generate_content(model=settings.gemini_model, contents=contents, config=config)
        except Exception as e:
            msg = str(e)
            transient = "503" in msg or "429" in msg or "UNAVAILABLE" in msg
            if not transient or i == attempts - 1:
                raise
            time.sleep(2 * (i + 1))


def _numbered(text: str) -> str:
    lines = text.splitlines()
    width = len(str(len(lines) or 1))
    return "\n".join(f"{i:>{width}} {ln}" for i, ln in enumerate(lines, start=1))


def _costs(session: Session, key: str, text: str, paths: list) -> tuple[int, int]:
    """(image_tokens, text_tokens) for one unit of context, cached per session."""
    if key not in session.file_text_tokens:
        session.file_text_tokens[key] = count_text(text)
    if key not in session.file_image_tokens:
        exact = count_images(paths)
        session.file_image_tokens[key] = exact if exact is not None else sum(
            estimate_image_tokens(*image_size(p)) for p in paths)
    return session.file_image_tokens[key], session.file_text_tokens[key]


def _source_text(session: Session, f: str) -> str:
    text = dict(session.grounding_texts).get(f)
    if text is None:
        text = safe_repo_path(session.repo_dir, f).read_text(encoding="utf-8")
    return text


def _text_entry(kind: str, title: str, file: str | None, tokens: int, img_tokens: int, reason: str) -> dict:
    return {"name": "", "kind": kind, "title": title, "file": file, "width": 0, "height": 0,
            "tokens_est": 0, "source": "text", "text_tokens": tokens, "image_tokens_avoided": img_tokens,
            "reason": f"{reason} | sent as text: {tokens:,} text tokens <= {img_tokens:,} image tokens"}


def _used(session: Session, path, kind: str, title: str) -> dict:
    w, h = image_size(path)
    return {"name": str(path.relative_to(session.context_dir)), "kind": kind, "title": title,
            "width": w, "height": h, "tokens_est": estimate_image_tokens(w, h)}


def answer(session: Session, message: str, open_file: str | None) -> dict:
    ctx = session.context_dir
    code_files = {i["file"] for i in session.images if i["kind"] == "code"}
    sel = select(message, open_file, session.graph, code_files)
    images_used: list[dict] = []  # every unit sent: an image, or a text entry when text was cheaper
    as_image_text_tokens = 0  # text cost of the content that WAS sent as images (for the comparison)
    sent_text_tokens = 0  # tokens spent on content sent as plain text

    # Graph/architecture/wiki pages only for structural questions (or when nothing specific matched).
    # Rendered JIT here if not already rendered during upload.
    if sel.include_grounding and session.grounding_combined and not any(i["kind"] == "context" for i in session.images):
        grounding_dir = ctx / "grounding"
        grounding_dir.mkdir(parents=True, exist_ok=True)
        paths = render_text_pages(session.grounding_combined, "repo grounding context", grounding_dir, 
                                  "grounding", "config", settings.max_grounding_pages - len(session.images))
        for p in paths:
            session.images.append(_used(session, p, "context", f"grounding pages ({session.grounding_titles})"))
            
    grounding_parts: list[types.Part] = []
    pages = [img for img in session.images if img["kind"] != "code"]
    if sel.include_grounding and pages:
        manifest = ", ".join(f"{i+1}={img['title']}" for i, img in enumerate(pages))
        grounding_parts = [types.Part(text=prompt.GROUNDING_INTRO.format(manifest=manifest))]
        body = "\n\n".join(f"FILE: {t}\n{b}" for t, b in session.grounding_texts if t not in code_files)
        img_t, txt_t = _costs(session, "__grounding__", body, [ctx / i["name"] for i in pages])
        if txt_t <= img_t:
            grounding_parts.append(types.Part(text=body))
            sent_text_tokens += txt_t
            images_used.append(_text_entry("context", "graph / architecture / wiki / docs", None, txt_t, img_t,
                                           "structural question"))
        else:
            as_image_text_tokens += txt_t
            for img in pages:
                grounding_parts.append(_image_part(ctx / img["name"]))
                images_used.append({**img, "source": "grounding", "reason": "structural question"})

    # Only the files picked through the graph, each as an image set or as text, whichever is cheaper.
    user_parts: list[types.Part] = []
    if sel.files:
        user_parts.append(types.Part(text=prompt.SELECTED_INTRO.format(files=", ".join(sel.files))))
    for f in sel.files:
        imgs = [i for i in session.images if i["kind"] == "code" and i["file"] == f]
        if imgs:
            paths = [ctx / i["name"] for i in imgs]
        else:  # e.g. the open file was over the per-file cap or not a rendered type
            paths = render_open_file(session, f)
            imgs = [{**_used(session, p, "file", f), "file": f} for p in paths]
        text = f"FILE: {f}\n{_numbered(_source_text(session, f))}"
        img_t, txt_t = _costs(session, f, text, paths)
        if txt_t <= img_t:
            user_parts.append(types.Part(text=text))
            sent_text_tokens += txt_t
            images_used.append(_text_entry("code", f, f, txt_t, img_t, sel.reasons[f]))
            continue
        as_image_text_tokens += txt_t
        for img, p in zip(imgs, paths):
            user_parts.append(types.Part(text=prompt.CODE_IMAGE_LABEL.format(
                path=f, page=img.get("page", 1), pages=img.get("pages", len(paths)))))
            user_parts.append(_image_part(p))
            images_used.append({**img, "source": "code" if "page" in img else "file", "reason": sel.reasons[f]})
    if session.graph is not None:
        for f in sel.files:
            user_parts.append(types.Part(text=prompt.GRAPH_SLICE_TEMPLATE.format(
                path=f, facts=graph_slice(session.graph, f))))
    if open_file:
        user_parts.append(types.Part(text=prompt.FILE_OPEN_NOTE.format(path=open_file)))
    user_parts.append(types.Part(text=prompt.QUESTION_TEMPLATE.format(question=message)))
    mode = sel.mode

    history = [types.Content(role="user" if h["role"] == "user" else "model",
                             parts=[types.Part(text=h["content"])])
               for h in session.history[-HISTORY_TURNS:]]
    contents: list[types.Content] = []
    if grounding_parts:
        contents += [types.Content(role="user", parts=grounding_parts),
                     types.Content(role="model", parts=[types.Part(text=prompt.GROUNDING_ACK)])]
    contents += history + [types.Content(role="user", parts=user_parts)]

    # max_output_tokens also counts thinking tokens, so keep it large and thinking low or answers get cut off.
    config = types.GenerateContentConfig(
        temperature=0.2, max_output_tokens=8192, system_instruction=prompt.SYSTEM_PROMPT,
        thinking_config=types.ThinkingConfig(thinking_level="low"))
    try:
        resp = _generate_with_retry(contents, config)
    except Exception as e:
        raise ChatError(f"Model call failed: {e}")

    u = resp.usage_metadata
    prompt_tokens = (u.prompt_token_count or 0) if u else 0
    image_tokens, _ = modality_tokens(u) if u else (None, None)
    if image_tokens is None:
        image_tokens = sum(i["tokens_est"] for i in images_used if i["source"] != "text")
    stats = {
        "image_tokens": image_tokens,  # what Gemini charged for the images
        "text_tokens": as_image_text_tokens,  # same content as the images, had it been sent as text
        "sent_as_text_tokens": sent_text_tokens,  # content that was sent as text because it was cheaper
        "units_as_text": sum(1 for i in images_used if i["source"] == "text"),
        "output_tokens": (u.candidates_token_count or 0) if u else 0,
        "images_used": sum(1 for i in images_used if i["source"] != "text"),
    }
    text = resp.text or "(no response)"
    if resp.candidates and str(resp.candidates[0].finish_reason).endswith("MAX_TOKENS"):
        text += "\n\n_(Answer was cut off at the output limit. Ask me to continue.)_"
    session.history.append({"role": "user", "content": message})
    session.history.append({"role": "assistant", "content": text, "context": mode,
                            "stats": stats, "images_used": images_used})
    return {"answer": text, "context_used": mode, "stats": stats, "images_used": images_used}
