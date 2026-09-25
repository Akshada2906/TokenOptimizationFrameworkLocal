"""Deterministic architecture scan: frameworks, entry points, folder structure -> architecture.md."""
import json
from collections import Counter
from pathlib import Path

from src.services.pixelprompt.graph import Graph
from src.services.pixelprompt.workspace import IGNORED_DIRS, iter_repo_files

LANGS = {".py": "Python", ".js": "JavaScript", ".jsx": "JavaScript", ".ts": "TypeScript",
         ".tsx": "TypeScript", ".java": "Java", ".go": "Go", ".rs": "Rust", ".rb": "Ruby",
         ".php": "PHP", ".cs": "C#", ".cpp": "C++", ".c": "C", ".kt": "Kotlin", ".swift": "Swift"}

FRAMEWORK_DEPS = {
    "fastapi": "FastAPI", "flask": "Flask", "django": "Django", "sqlalchemy": "SQLAlchemy",
    "celery": "Celery", "pydantic": "Pydantic", "langchain": "LangChain",
    "react": "React", "next": "Next.js", "vue": "Vue", "svelte": "Svelte", "express": "Express",
    "nestjs": "NestJS", "@nestjs/core": "NestJS", "vite": "Vite", "angular": "Angular",
    "spring-boot": "Spring Boot", "gin-gonic/gin": "Gin", "actix-web": "Actix",
}
ENTRY_NAMES = {"main.py", "app.py", "manage.py", "wsgi.py", "asgi.py", "__main__.py", "server.py",
               "index.js", "server.js", "app.js", "index.ts", "main.ts", "main.tsx", "index.tsx",
               "main.go", "main.rs", "Main.java", "Application.java"}


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def detect_frameworks(repo: Path) -> list[str]:
    found: set[str] = set()
    for p in iter_repo_files(repo):
        depth = len(p.relative_to(repo).parts)
        if depth > 3:
            continue
        low_deps = ""
        if p.name == "package.json":
            try:
                pkg = json.loads(_read(p))
                low_deps = " ".join(list(pkg.get("dependencies", {})) + list(pkg.get("devDependencies", {})))
            except json.JSONDecodeError:
                pass
        elif p.name in {"requirements.txt", "pyproject.toml", "Pipfile", "pom.xml",
                        "build.gradle", "go.mod", "Cargo.toml", "Gemfile", "composer.json"}:
            low_deps = _read(p).lower()
        if low_deps:
            tokens = set(low_deps.replace("\n", " ").replace('"', " ").replace("=", " ").split())
            for key, name in FRAMEWORK_DEPS.items():
                if key in tokens or any(t.startswith(key) for t in tokens) or f"/{key}" in low_deps:
                    found.add(name)
    return sorted(found)


def detect_entry_points(repo: Path) -> list[str]:
    out = []
    for p in iter_repo_files(repo):
        rel = p.relative_to(repo)
        if p.name in ENTRY_NAMES and len(rel.parts) <= 4:
            out.append(str(rel))
        elif p.name == "package.json" and len(rel.parts) <= 3:
            try:
                pkg = json.loads(_read(p))
            except json.JSONDecodeError:
                continue
            if pkg.get("main"):
                out.append(f"{rel} (main: {pkg['main']})")
            for name in ("dev", "start", "build"):
                if name in pkg.get("scripts", {}):
                    out.append(f"{rel} script `{name}`: {pkg['scripts'][name]}")
    return out[:25]


def folder_structure(repo: Path, max_depth: int = 2) -> list[str]:
    lines: list[str] = []

    def count(d: Path) -> int:
        return sum(1 for f in iter_repo_files(d))

    def walk(d: Path, depth: int) -> None:
        for c in sorted(d.iterdir(), key=lambda p: p.name.lower()):
            if c.is_dir() and c.name not in IGNORED_DIRS and not c.is_symlink():
                lines.append(f"{'  ' * depth}- {c.name}/ ({count(c)} files)")
                if depth + 1 < max_depth:
                    walk(c, depth + 1)

    walk(repo, 0)
    return lines[:120]


def build_architecture_md(repo: Path, graph: Graph | None, graph_source: str) -> str:
    langs = Counter(LANGS[p.suffix] for p in iter_repo_files(repo) if p.suffix in LANGS)
    frameworks = detect_frameworks(repo)
    entries = detect_entry_points(repo)
    md = [f"# Architecture summary: {repo.name}", ""]
    md.append("## Languages\n" + (", ".join(f"{k} ({v} files)" for k, v in langs.most_common()) or "unknown"))
    md.append("\n## Frameworks / tooling\n" + (", ".join(frameworks) or "none detected"))
    md.append("\n## Entry points\n" + ("\n".join(f"- {e}" for e in entries) or "- none detected"))
    md.append("\n## Folder structure\n" + "\n".join(folder_structure(repo)))
    if graph:
        deg = graph.degree()
        top = sorted(deg.items(), key=lambda kv: -kv[1])[:10]
        md.append(f"\n## Dependency graph ({graph_source})\n{len(graph.nodes)} nodes, {len(graph.edges)} edges.")
        md.append("Core (most connected) symbols:")
        md += [f"- {graph.nodes[n]['label']} [{graph.nodes[n]['file']}] degree={d}"
               for n, d in top if n in graph.nodes]
    return "\n".join(md) + "\n"
