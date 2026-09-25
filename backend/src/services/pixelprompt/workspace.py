import os
import subprocess
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from src.config.settings import settings

IGNORED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    ".next", ".idea", ".vscode", "graphify-out", "code-review-graph", ".mypy_cache", ".pytest_cache", "target",
}


CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".java", ".go", ".rs", ".rb", ".php",
    ".cs", ".c", ".h", ".cc", ".cpp", ".hpp", ".kt", ".swift", ".scala", ".sh", ".bash", ".sql",
    ".html", ".css", ".scss", ".vue", ".svelte", ".md", ".mdx", ".json", ".yml", ".yaml",
    ".toml", ".ini", ".cfg", ".xml", ".gradle", ".proto", ".graphql",
}
CODE_NAMES = {"Dockerfile", "Makefile", "requirements.txt", "go.mod", "Gemfile", ".env.example"}
SKIP_NAMES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock"}
MAX_UPLOAD_FILE_BYTES = 1_000_000


def is_code_file(rel: str, size: int = 0) -> bool:
    """Only real source/config/doc files are analyzed; images, binaries, lockfiles, bundles are not."""
    name = PurePosixPath(rel.replace("\\", "/")).name
    if name in SKIP_NAMES or name.endswith((".min.js", ".min.css", ".map")):
        return False
    if size > MAX_UPLOAD_FILE_BYTES:
        return False
    return name in CODE_NAMES or PurePosixPath(name).suffix.lower() in CODE_EXTS


GRAPH_DIR = "code-review-graph"  # where the graph lives inside the repo (renamed from Graphify's graphify-out)
GRAPH_DIRS = {"graphify-out", GRAPH_DIR}
GITIGNORE_BLOCK = f"# RepoGraph code review graph (generated)\n{GRAPH_DIR}/\n"


class WorkspaceError(Exception):
    pass


def validate_repo_url(url: str) -> str:
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise WorkspaceError("Only https:// repository URLs are supported.")
    if parsed.username or parsed.password:
        raise WorkspaceError("Credentials in URLs are not allowed.")
    if parsed.hostname.lower() not in settings.allowed_git_hosts:
        raise WorkspaceError(
            f"Host not allowed. Allowed: {', '.join(settings.allowed_git_hosts)}"
        )
    return url


def ensure_gitignore(repo: Path) -> bool:
    """Make sure code-review-graph/ is git-ignored in the repo. Returns True if the file was changed."""
    gi = repo / ".gitignore"
    try:
        current = gi.read_text(encoding="utf-8") if gi.exists() else ""
        if any(line.strip().rstrip("/").lstrip("/") == GRAPH_DIR for line in current.splitlines()):
            return False
        sep = "" if not current or current.endswith("\n") else "\n"
        gi.write_text(current + sep + ("\n" if current else "") + GITIGNORE_BLOCK, encoding="utf-8")
        return True
    except OSError:
        return False


def validate_local_path(raw: str) -> Path:
    p = Path(raw).expanduser()
    if not p.is_absolute():
        raise WorkspaceError("Enter an absolute folder path.")
    p = p.resolve()
    if not p.is_dir():
        raise WorkspaceError(f"Folder not found: {p}")
    if p == Path("/") or p == Path.home():
        raise WorkspaceError("Choose a project folder, not the filesystem root or your home folder.")
    return p


def clone_repo(url: str, dest: Path) -> None:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    cmd = [
        "git", "-c", "core.hooksPath=/dev/null", "-c", "core.symlinks=false",
        "clone", "--depth=1", "--no-tags", "--single-branch", "--", url, str(dest),
    ]
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=settings.clone_timeout_s, env=env
        )
    except subprocess.TimeoutExpired:
        raise WorkspaceError("git clone timed out.")
    if proc.returncode != 0:
        raise WorkspaceError(f"git clone failed: {proc.stderr.strip()[-300:]}")
    check_repo_limits(dest)


def save_upload(files: list[tuple[str, bytes]], dest: Path) -> None:
    """files: (relative_path, content). Rejects traversal, absolute paths and oversize uploads."""
    dest.mkdir(parents=True, exist_ok=True)
    if len(files) > settings.max_repo_files:
        raise WorkspaceError("Too many files in upload.")
    total = 0
    root = dest.resolve()
    for rel, data in files:
        posix = PurePosixPath(rel.replace("\\", "/"))
        if posix.is_absolute() or ".." in posix.parts or not posix.parts:
            raise WorkspaceError(f"Unsafe path in upload: {rel}")
        if any(part in IGNORED_DIRS - GRAPH_DIRS for part in posix.parts):
            continue
        if not is_code_file(rel, len(data)):
            continue
        total += len(data)
        if total > settings.max_repo_mb * 1024 * 1024:
            raise WorkspaceError("Upload too large.")
        target = (dest / Path(*posix.parts)).resolve()
        if root not in target.parents:
            raise WorkspaceError(f"Unsafe path in upload: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    if not any(dest.iterdir()):
        raise WorkspaceError("No source code files found in the upload.")
    _flatten_single_root(dest)


def _flatten_single_root(dest: Path) -> None:
    """Folder uploads arrive as <folder>/...; hoist the single top-level folder."""
    entries = list(dest.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        inner = entries[0]
        for child in list(inner.iterdir()):
            child.rename(dest / child.name)
        inner.rmdir()


def check_repo_limits(repo: Path) -> None:
    count = size = 0
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = [d for d in dirnames if d != ".git"]
        for f in filenames:
            count += 1
            try:
                size += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    if count > settings.max_repo_files or size > settings.max_repo_mb * 1024 * 1024:
        raise WorkspaceError("Repository exceeds size/file limits.")


def iter_repo_files(repo: Path):
    for dirpath, dirnames, filenames in os.walk(repo):
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRS)
        for f in sorted(filenames):
            yield Path(dirpath) / f


def build_tree(repo: Path, limit: int = 6000) -> list[dict]:
    counter = [0]

    def walk(directory: Path) -> list[dict]:
        nodes: list[dict] = []
        try:
            entries = sorted(directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        except OSError:
            return nodes
        for p in entries:
            if counter[0] >= limit or p.is_symlink():
                continue
            if p.is_dir():
                if p.name in IGNORED_DIRS:
                    continue
                counter[0] += 1
                nodes.append({"name": p.name, "path": str(p.relative_to(repo)), "type": "dir",
                              "children": walk(p)})
            else:
                counter[0] += 1
                nodes.append({"name": p.name, "path": str(p.relative_to(repo)), "type": "file"})
        return nodes

    return walk(repo)


def safe_repo_path(repo: Path, rel: str) -> Path:
    target = (repo / rel).resolve()
    if repo.resolve() not in target.parents and target != repo.resolve():
        raise WorkspaceError("Path escapes repository.")
    return target
