from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env", extra="ignore", case_sensitive=False
    )

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    # Cloned/uploaded repos, Graphify output and rendered images live here, outside this project.
    workspace_root: Path = Path.home() / ".repograph" / "workspaces"
    session_ttl_s: int = 6 * 3600

    allow_local_paths: bool = True  # analyze a local folder in place (this app runs on your machine)
    allowed_git_hosts: list[str] = ["github.com", "gitlab.com", "bitbucket.org"]
    clone_timeout_s: int = 180
    graphify_timeout_s: int = 300
    max_repo_mb: int = 200
    max_repo_files: int = 20000
    max_file_view_bytes: int = 1_000_000

    # PixelPrompt rendering (library: pixelprompt)
    pixel_page_px: int = 1536  # max page edge; 2x2 Gemini tiles
    pixel_font_px: int | None = None  # None = use the PixelPrompt content-type preset
    pixel_file_font_px: int = 10  # open files are read line by line, so render them larger than the 'code' preset (7)
    pixel_code_font_px: int = 9  # per-file code images
    max_code_images: int = 200  # safety cap on per-file images sent every turn
    max_code_file_bytes: int = 200_000
    max_grounding_pages: int = 12
    max_file_pages: int = 4

    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
settings.workspace_root.mkdir(parents=True, exist_ok=True)
