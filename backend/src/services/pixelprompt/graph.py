"""Load a dependency/call graph (Graphify or code-review-graph JSON) into one neutral shape."""
import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Graph:
    nodes: dict[str, dict] = field(default_factory=dict)  # id -> {label, file, community, kind}
    edges: list[dict] = field(default_factory=list)  # {source, target, relation}

    def degree(self) -> dict[str, int]:
        d: dict[str, int] = defaultdict(int)
        for e in self.edges:
            d[e["source"]] += 1
            d[e["target"]] += 1
        return d


def _rel(path: str | None, repo: Path | None) -> str:
    if not path:
        return ""
    if repo is not None:
        try:
            return str(Path(path).resolve().relative_to(repo.resolve()))
        except (ValueError, OSError):
            pass
        # Graphify writes paths relative to its scan root's parent, e.g. "repo/src/a.py"
        parts = Path(path).parts
        if parts and parts[0] == repo.name:
            return str(Path(*parts[1:]))
    return path


def _strip_foreign_prefix(g: "Graph") -> None:
    """Graphs generated elsewhere carry absolute paths of another machine; strip the common prefix."""
    files = [n["file"] for n in g.nodes.values() if n["file"].startswith("/")]
    if not files:
        return
    import os
    prefix = os.path.commonpath(files) if len(files) > 1 else os.path.dirname(files[0])
    for n in g.nodes.values():
        if n["file"].startswith(prefix):
            n["file"] = n["file"][len(prefix):].lstrip("/")


def load_graph(path: Path, repo: Path | None = None) -> Graph:
    data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    g = Graph()
    alias: dict[str, str] = {}
    for n in data.get("nodes", []):
        nid = str(n.get("id"))
        g.nodes[nid] = {
            "label": n.get("label") or n.get("name") or nid,
            "file": _rel(n.get("source_file") or n.get("file_path"), repo),
            "community": n.get("community", n.get("community_id")),
            "community_name": n.get("community_name"),
            "kind": n.get("kind") or n.get("file_type") or "",
        }
        if n.get("qualified_name"):
            alias[str(n["qualified_name"])] = nid
    _strip_foreign_prefix(g)
    raw_edges = data.get("links") or data.get("edges") or []
    for e in raw_edges:
        s = str(e.get("source", e.get("source_qualified", "")))
        t = str(e.get("target", e.get("target_qualified", "")))
        s, t = alias.get(s, s), alias.get(t, t)
        g.edges.append({"source": s, "target": t,
                        "relation": e.get("relation") or e.get("kind") or "related"})
    return g


def file_edges(g: Graph) -> dict[tuple[str, str], int]:
    """Collapse to file-level dependency edges (file A -> file B, count)."""
    out: dict[tuple[str, str], int] = defaultdict(int)
    for e in g.edges:
        a, b = g.nodes.get(e["source"]), g.nodes.get(e["target"])
        if a and b and a["file"] and b["file"] and a["file"] != b["file"]:
            out[(a["file"], b["file"])] += 1
    return out


def graph_slice(g: Graph, rel_path: str, limit: int = 40) -> str:
    """Deterministic facts about one file: its symbols, what it depends on, who depends on it."""
    ids = {i for i, n in g.nodes.items()
           if n["file"] and (n["file"] == rel_path or rel_path.endswith("/" + n["file"]))}
    if not ids:
        return "No graph nodes recorded for this file."
    lines = []
    symbols = sorted({g.nodes[i]["label"] for i in ids})
    lines.append("Symbols: " + ", ".join(symbols[:limit]))
    out_l, in_l = [], []
    for e in g.edges:
        s, t = e["source"], e["target"]
        if s in ids and t not in ids:
            tn = g.nodes.get(t, {})
            out_l.append(f"- {g.nodes[s]['label']} --{e['relation']}--> {tn.get('label', t)}"
                         + (f" ({tn['file']})" if tn.get("file") else ""))
        elif t in ids and s not in ids:
            sn = g.nodes.get(s, {})
            in_l.append(f"- {sn.get('label', s)}" + (f" ({sn['file']})" if sn.get("file") else "")
                        + f" --{e['relation']}--> {g.nodes[t]['label']}")
    lines.append("Depends on / calls:\n" + ("\n".join(sorted(set(out_l))[:limit]) or "- none"))
    lines.append("Used by / called by:\n" + ("\n".join(sorted(set(in_l))[:limit]) or "- none"))
    return "\n".join(lines)


def graph_summary_text(g: Graph, top: int = 30, edge_cap: int = 250) -> str:
    deg = g.degree()
    lines = [f"# Graph summary: {len(g.nodes)} nodes, {len(g.edges)} edges", ""]
    lines.append("## Most connected symbols")
    for nid, d in sorted(deg.items(), key=lambda kv: -kv[1])[:top]:
        n = g.nodes.get(nid)
        if n:
            lines.append(f"- {n['label']} [{n['file']}] degree={d}")
    comms: dict[object, list[str]] = defaultdict(list)
    names: dict[object, str] = {}
    for n in g.nodes.values():
        comms[n["community"]].append(n["label"])
        if n.get("community_name"):
            names[n["community"]] = n["community_name"]
    lines += ["", "## Communities"]
    for c, members in sorted(comms.items(), key=lambda kv: -len(kv[1]))[:20]:
        lines.append(f"- {names.get(c, c)} ({len(members)}): " + ", ".join(sorted(members)[:15]))
    fe = sorted(file_edges(g).items(), key=lambda kv: -kv[1])[:edge_cap]
    lines += ["", "## File dependencies (A -> B, edge count)"]
    lines += [f"{a} -> {b} ({c})" for (a, b), c in fe]
    return "\n".join(lines)
