"""Find an existing code graph / docs in the repo, or build one with Graphify (AST-only, no LLM)."""
import ast
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from src.config.settings import settings
from src.services.workspace import IGNORED_DIRS, iter_repo_files

DOC_HINTS = ("architecture", "design", "overview", "readme", "diagram", "flow", "structure", "adr")
MAX_DOC_CHARS = 30_000
MAX_DOCS_TOTAL = 120_000


@dataclass
class AnalysisResult:
    graph_json: Path | None = None
    graph_report: Path | None = None
    source: str = "none"  # existing | graphify | fallback
    docs: list[Path] = field(default_factory=list)
    wiki: list[Path] = field(default_factory=list)  # Graphify wiki markdown: index.md first
    notes: list[str] = field(default_factory=list)


def _looks_like_graph(p: Path) -> bool:
    try:
        with p.open("rb") as f:
            head = f.read(4096)
        return b'"nodes"' in head or b'"links"' in head
    except OSError:
        return False


def find_existing_graph(repo: Path) -> tuple[Path | None, Path | None]:
    graph = report = None
    for dirpath, dirnames, filenames in os.walk(repo):
        depth = Path(dirpath).relative_to(repo).parts
        dirnames[:] = [d for d in dirnames if d not in (IGNORED_DIRS - {"graphify-out"})]
        if len(depth) > 4:
            dirnames[:] = []
        for f in filenames:
            p = Path(dirpath) / f
            if f == "graph.json" and graph is None and _looks_like_graph(p):
                graph = p
            elif f == "GRAPH_REPORT.md" and report is None:
                report = p
    return graph, report


def collect_docs(repo: Path) -> list[Path]:
    md = [p for p in iter_repo_files(repo) if p.suffix.lower() == ".md" and p.name != "GRAPH_REPORT.md"]

    def rank(p: Path) -> tuple[int, int]:
        name = str(p.relative_to(repo)).lower()
        hint = 0 if any(h in name for h in DOC_HINTS) else 1
        return (hint, len(p.relative_to(repo).parts))

    chosen, total = [], 0
    for p in sorted(md, key=rank):
        size = min(p.stat().st_size, MAX_DOC_CHARS)
        if total + size > MAX_DOCS_TOTAL:
            continue
        chosen.append(p)
        total += size
    return chosen


def run_graphify(repo: Path) -> bool:
    exe = shutil.which("graphify") or str(Path(sys.executable).parent / "graphify")
    if not Path(exe).exists() and not shutil.which("graphify"):
        return False
    try:
        proc = subprocess.run(
            [exe, "update", str(repo)], capture_output=True, text=True,
            timeout=settings.graphify_timeout_s, cwd=repo.parent,
            env={**os.environ, "GRAPHIFY_NO_LLM": "1"},
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    ok = proc.returncode == 0 and (repo / "graphify-out" / "graph.json").exists()
    if ok:  # markdown wiki (index.md + community articles); best-effort
        try:
            subprocess.run([exe, "export", "wiki"], capture_output=True, text=True,
                           timeout=settings.graphify_timeout_s, cwd=repo)
        except (subprocess.TimeoutExpired, OSError):
            pass
    return ok


def collect_wiki(graph_json: Path | None, cap_chars: int = 40_000) -> list[Path]:
    """Graphify wiki markdown next to graph.json (index.md first, then largest articles)."""
    if not graph_json:
        return []
    wiki = graph_json.parent / "wiki"
    if not wiki.is_dir():
        return []
    index = wiki / "index.md"
    articles = sorted((p for p in wiki.glob("*.md") if p.name != "index.md"),
                      key=lambda p: -p.stat().st_size)
    chosen, total = ([index] if index.exists() else []), 0
    for p in articles:
        if total + p.stat().st_size > cap_chars:
            continue
        chosen.append(p)
        total += p.stat().st_size
    return chosen


_JS_IMPORT = re.compile(r"""(?:import\s[^'"]*?from\s*|import\s*\(?\s*|require\(\s*)['"]([^'"]+)['"]""")


def fallback_scan(repo: Path) -> Path:
    """Minimal import scanner (py/js/ts) used only if Graphify is unavailable or fails."""
    files = [p for p in iter_repo_files(repo)
             if p.suffix in {".py", ".js", ".jsx", ".ts", ".tsx", ".mjs"}]
    rel = {str(p.relative_to(repo)): p for p in files}
    mod_index = {r[:-3].replace("/", "."): r for r in rel if r.endswith(".py")}
    nodes = [{"id": r, "label": Path(r).name, "source_file": r, "community": r.split("/")[0]}
             for r in rel]
    links = []
    for r, p in rel.items():
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        targets: set[str] = set()
        if p.suffix == ".py":
            try:
                for n in ast.walk(ast.parse(text)):
                    names = []
                    if isinstance(n, ast.Import):
                        names = [a.name for a in n.names]
                    elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
                        names = [n.module] + [f"{n.module}.{a.name}" for a in n.names]
                    for m in names:
                        if m in mod_index:
                            targets.add(mod_index[m])
                        elif f"{m}.__init__" in mod_index:
                            targets.add(mod_index[f"{m}.__init__"])
            except SyntaxError:
                pass
        else:
            for m in _JS_IMPORT.findall(text):
                if m.startswith("."):
                    base = (Path(r).parent / m).as_posix()
                    base = os.path.normpath(base)
                    for cand in [base] + [base + e for e in (".ts", ".tsx", ".js", ".jsx")] + \
                                [f"{base}/index{e}" for e in (".ts", ".tsx", ".js", ".jsx")]:
                        if cand in rel:
                            targets.add(cand)
                            break
        for t in targets:
            if t != r:
                links.append({"source": r, "target": t, "relation": "imports"})
    out = repo.parent / "context" / "fallback_graph.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"nodes": nodes, "links": links}))
    return out


def analyze(repo: Path) -> AnalysisResult:
    res = AnalysisResult(docs=collect_docs(repo))
    graph, report = find_existing_graph(repo)
    if graph:
        res.graph_json, res.graph_report, res.source = graph, report, "existing"
        res.wiki = collect_wiki(graph)
        res.notes.append(f"Using existing graph at {graph.relative_to(repo)}")
        return res
    if run_graphify(repo):
        res.graph_json = repo / "graphify-out" / "graph.json"
        rep = repo / "graphify-out" / "GRAPH_REPORT.md"
        res.graph_report = rep if rep.exists() else None
        res.source = "graphify"
        res.wiki = collect_wiki(res.graph_json)
        res.notes.append("Graph built with Graphify")
        return res
    res.graph_json = fallback_scan(repo)
    res.source = "fallback"
    res.notes.append("Graphify unavailable/failed; used fallback import scanner")
    return res
