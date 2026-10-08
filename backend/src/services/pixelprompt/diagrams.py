"""Dependency diagrams from the graph (Graphviz `dot`; skipped gracefully if not installed)."""
import shutil
import subprocess
from collections import defaultdict
from pathlib import Path

from src.services.pixelprompt.graph import Graph, file_edges


def _pkg(path: str, depth: int) -> str:
    parts = Path(path).parts
    return "/".join(parts[:depth]) if len(parts) > depth else (str(Path(path).parent) or ".")


def build_dot(g: Graph, max_nodes: int = 45) -> str | None:
    fe = file_edges(g)
    if not fe:
        return None
    for depth in (3, 2, 1):  # coarsen until the diagram is readable
        agg: dict[tuple[str, str], int] = defaultdict(int)
        for (a, b), c in fe.items():
            pa, pb = _pkg(a, depth), _pkg(b, depth)
            if pa != pb:
                agg[(pa, pb)] += c
        nodes = {n for e in agg for n in e}
        if 2 <= len(nodes) <= max_nodes:
            break
    if not agg:
        return None
    lines = ['digraph G {', 'rankdir=LR; dpi=110; bgcolor="white";',
             'node [shape=box, style="rounded,filled", fillcolor="#eef2ff", color="#6366f1", '
             'fontname="Helvetica", fontsize=13];', 'edge [color="#64748b", fontname="Helvetica", fontsize=10];']
    for (a, b), c in sorted(agg.items(), key=lambda kv: -kv[1])[:150]:
        lines.append(f'"{a}" -> "{b}" [label="{c}"];')
    lines.append("}")
    return "\n".join(lines)


def render_diagrams(g: Graph, out_dir: Path) -> list[Path]:
    dot_src = build_dot(g)
    dot = shutil.which("dot")
    if not dot_src or not dot:
        return []
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "dependencies.dot").write_text(dot_src)
    made = []
    for fmt in ("png", "svg"):
        target = out_dir / f"dependencies.{fmt}"
        try:
            subprocess.run([dot, f"-T{fmt}", "-o", str(target)], input=dot_src, text=True,
                           check=True, capture_output=True, timeout=60)
            made.append(target)
        except (subprocess.SubprocessError, OSError):
            pass
    return made
