"""Decide which images a question needs, using the code graph.

Instead of sending every image on every turn, the question is matched against file paths and graph
symbols; only the matching files (plus their direct graph neighbours and the open file) are sent as
images. The graph/architecture/wiki pages are added only for structural questions, or when nothing
specific matched.
"""
import re
from collections import defaultdict
from dataclasses import dataclass, field

MAX_MATCHED = 3  # files that matched the question directly
MAX_NEIGHBOURS = 3  # extra files pulled in through graph edges
MAX_FILES = 6

STRUCTURAL_WORDS = {
    "architecture", "overview", "structure", "structural", "entry", "entrypoint", "entrypoints",
    "project", "repo", "repository", "codebase", "stack", "framework", "frameworks", "libraries",
    "library", "dependencies", "dependency", "requirements", "folders", "folder", "layout",
    "modules", "diagram", "graph", "communities",
}
STOP = {
    "the", "a", "an", "is", "are", "of", "in", "on", "to", "for", "and", "or", "how", "what",
    "where", "why", "which", "does", "do", "this", "that", "it", "with", "from", "me", "my",
    "can", "you", "any", "there", "about", "file", "code", "function", "class", "method",
}


@dataclass
class Selection:
    mode: str  # 'structural' | 'files' | 'both'
    include_grounding: bool
    files: list[str] = field(default_factory=list)  # repo-relative, in priority order
    reasons: dict[str, str] = field(default_factory=dict)  # file -> why it was picked


def _tokens(text: str) -> set[str]:
    # split camelCase / snake_case / paths so "renderTextPages" matches "render_text_pages"
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", text)
    return {t for t in re.split(r"[^A-Za-z0-9]+", text.lower()) if len(t) > 2 and t not in STOP}


def _same(a: str, b: str) -> bool:
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def select(message: str, open_file: str | None, graph, code_files: set[str]) -> Selection:
    """code_files: files that have code images available."""
    q_tokens = _tokens(message)
    lowered = message.lower()
    structural = bool(q_tokens & STRUCTURAL_WORDS)

    score: dict[str, float] = defaultdict(float)
    reasons: dict[str, str] = {}

    def bump(f: str, s: float, why: str):
        score[f] += s
        reasons.setdefault(f, why)

    for f in code_files:
        base = f.rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0]
        if f.lower() in lowered:
            bump(f, 10, "path named in question")
        elif base.lower() in lowered or (len(stem) > 3 and re.search(rf"\b{re.escape(stem.lower())}\b", lowered)):
            bump(f, 8, "file named in question")
        else:
            overlap = q_tokens & _tokens(f)
            if overlap:
                bump(f, 2 * len(overlap), "path matches: " + ", ".join(sorted(overlap)))

    if graph is not None:
        for n in graph.nodes.values():
            f = n.get("file")
            label = str(n.get("label") or "")
            if not f or not label:
                continue
            target = next((c for c in code_files if _same(c, f)), None)
            if not target:
                continue
            lt = _tokens(label)
            if len(label) > 3 and re.search(rf"\b{re.escape(label.lower().rstrip('()'))}\b", lowered):
                bump(target, 6, f"symbol in graph: {label}")
            elif lt and lt <= q_tokens and len(lt) >= 2:
                bump(target, 4, f"symbol in graph: {label}")

    matched = [f for f, _ in sorted(score.items(), key=lambda kv: -kv[1])][:MAX_MATCHED]

    files: list[str] = []
    picked_reasons: dict[str, str] = {}
    if open_file:
        target = next((c for c in code_files if _same(c, open_file)), open_file)
        files.append(target)
        picked_reasons[target] = "open file"
    for f in matched:
        if f not in files:
            files.append(f)
            picked_reasons[f] = reasons[f]

    # One hop through the graph from the matched files: their callers / dependencies.
    if graph is not None and matched:
        from src.services.pixelprompt.graph import file_edges
        touch: dict[str, int] = defaultdict(int)
        for (a, b), c in file_edges(graph).items():
            for m in matched:
                if _same(a, m):
                    touch[b] += c
                elif _same(b, m):
                    touch[a] += c
        added = 0
        for f, _ in sorted(touch.items(), key=lambda kv: -kv[1]):
            target = next((c for c in code_files if _same(c, f)), None)
            if target and target not in files and added < MAX_NEIGHBOURS:
                files.append(target)
                picked_reasons[target] = "graph neighbour of a matched file"
                added += 1
    files = files[:MAX_FILES]

    include_grounding = structural or not files
    if not files:
        mode = "structural"
    elif include_grounding:
        mode = "both"
    else:
        mode = "files"
    return Selection(mode, include_grounding, files, {f: picked_reasons[f] for f in files})
