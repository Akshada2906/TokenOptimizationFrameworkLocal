"""Session pipeline: clone/upload -> analyze -> architecture + diagrams -> PixelPrompt grounding images."""
import logging
import shutil

from src.config.settings import settings
from src.helpers.pixel_renderer import estimate_image_tokens, fit_image, image_size, render_text_pages
from src.services.pixelprompt.analyzer import analyze
from src.services.pixelprompt.architecture import build_architecture_md
from src.services.pixelprompt.code_context import render_code_images
from src.services.pixelprompt.diagrams import render_diagrams
from src.services.pixelprompt.graph import Graph, graph_summary_text, load_graph
from src.services.pixelprompt.session_store import Session
from src.services.pixelprompt.tokens import grounding_comparison
from src.services.pixelprompt.workspace import WorkspaceError, clone_repo, iter_repo_files

log = logging.getLogger(__name__)

TEXT_EXTS = {".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".rb", ".php", ".cs",
             ".cpp", ".c", ".h", ".kt", ".swift", ".md", ".json", ".yml", ".yaml", ".toml",
             ".html", ".css", ".sql", ".sh"}


def run_pipeline(session: Session, repo_url: str | None) -> None:
    try:
        if repo_url:
            session.status = "cloning"
            clone_repo(repo_url, session.repo_dir)
        session.status = "analyzing"
        _analyze_and_render(session)
        session.status = "ready"
    except WorkspaceError as e:
        session.status, session.error = "error", str(e)
    except Exception as e:  # keep the API responsive; surface the message to the UI
        log.exception("pipeline failed")
        session.status, session.error = "error", f"Unexpected error: {e}"


def _raw_repo_tokens(session: Session) -> tuple[int, int]:
    chars = files = 0
    for p in iter_repo_files(session.repo_dir):
        if p.suffix.lower() in TEXT_EXTS:
            try:
                chars += min(p.stat().st_size, 500_000)
                files += 1
            except OSError:
                pass
    return chars // 4, files  # ~4 chars per token


def _analyze_and_render(session: Session) -> None:
    repo, ctx = session.repo_dir, session.context_dir
    result = analyze(repo)
    graph: Graph | None = None
    if result.graph_json:
        try:
            graph = load_graph(result.graph_json, repo)
        except (OSError, ValueError) as e:
            result.notes.append(f"Could not parse graph: {e}")
    session.graph = graph
    session.graph_dir = result.graph_json.parent if result.graph_json and result.source != "fallback" else None
    session.graph_generated = result.source == "graphify"

    arch_md = build_architecture_md(repo, graph, result.source)
    (ctx / "architecture.md").write_text(arch_md, encoding="utf-8")
    diagrams = render_diagrams(graph, ctx / "diagrams") if graph else []

    session.status = "rendering"
    # (title, kind, text, max_pages, pixelprompt content type)
    sources: list[tuple[str, str, str, int, str]] = []
    sources.append(("architecture.md", "architecture", arch_md, 2, "prose"))
    if graph:
        sources.append(("graph summary", "graph", graph_summary_text(graph), 4, "config"))
    if result.graph_report:
        sources.append(("GRAPH_REPORT.md", "report", result.graph_report.read_text(errors="ignore")[:60_000], 3, "prose"))
    if result.wiki:
        wiki_text = "\n\n".join(p.read_text(errors="ignore") for p in result.wiki)
        sources.append(("graphify wiki (index.md + community articles)", "wiki", wiki_text, 2, "prose"))
    for doc in result.docs[:8]:
        sources.append((str(doc.relative_to(repo)), "doc", doc.read_text(errors="ignore")[:30_000], 2, "prose"))

    images: list[dict] = []
    grounding_dir = ctx / "grounding"
    if grounding_dir.exists():
        shutil.rmtree(grounding_dir)
    png = next((d for d in diagrams if d.suffix == ".png"), None)
    dot = ctx / "diagrams" / "dependencies.dot"
    session.grounding_texts = [(t, txt) for t, _k, txt, _m, _c in sources]
    if png and dot.exists():
        session.grounding_texts.append(("dependency diagram (dot source)", dot.read_text()))
    if png:
        dest = fit_image(png, grounding_dir / "diagram_dependencies.png")
        images.append(_entry(dest, "diagram", "dependency diagram", ctx))

    # Gemini charges a flat ~1k tokens per image regardless of size, so pack every text source
    # into one document and render it as few, full pages as possible.
    combined = "\n\n".join(f"=== {title} ===\n{_squeeze(text)}" for title, _k, text, _m, _c in sources)
    pages = render_text_pages(combined, "repo grounding context", grounding_dir, "grounding",
                              "config", settings.max_grounding_pages - len(images))
    titles = ", ".join(t for t, *_ in sources)
    for p in pages:
        images.append(_entry(p, "context", f"grounding pages ({titles})", ctx))
    # Every code file gets its own image(s): this is what lets the assistant read any file.
    code_entries, code_texts, included, omitted = render_code_images(repo, graph, ctx / "grounding" / "code")
    session.grounding_texts += code_texts
    for e in code_entries:
        img = _entry(e["path"], "code", e["title"], ctx)
        img.update({"file": e["file"], "page": e["page"], "pages": e["pages"]})
        images.append(img)
    session.omitted_files = omitted
    session.images = images

    raw_tokens, n_files = _raw_repo_tokens(session)
    image_tokens = sum(i["tokens_est"] for i in images)
    session.stats = {
        "files": n_files,
        "graph_nodes": len(graph.nodes) if graph else 0,
        "graph_edges": len(graph.edges) if graph else 0,
        "graph_source": result.source,
        "images": len(images),
        "grounding_image_tokens_est": image_tokens,
        "raw_repo_tokens_est": raw_tokens,
        "graph_dir": str(session.graph_dir) if session.graph_dir else None,
        "code_files": len(included),
        "code_files_omitted": len(omitted),
        "notes": result.notes,
        "has_diagram_svg": (ctx / "diagrams" / "dependencies.svg").exists(),
    }
    if settings.gemini_api_key:
        session.stats.update(grounding_comparison(session))  # exact counts via the API


def _squeeze(text: str) -> str:
    """Drop blank lines and markdown heading marks to keep rendered pages dense."""
    lines = (ln.rstrip().lstrip("#").strip() if ln.lstrip().startswith("#") else ln.rstrip()
             for ln in text.splitlines())
    return "\n".join(ln for ln in lines if ln.strip())


def _entry(path, kind: str, title: str, ctx) -> dict:
    w, h = image_size(path)
    return {"name": str(path.relative_to(ctx)), "kind": kind, "title": title,
            "width": w, "height": h, "tokens_est": estimate_image_tokens(w, h)}
