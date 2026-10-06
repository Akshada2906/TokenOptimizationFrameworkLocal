import os
from pathlib import Path

repo = Path.home() / '.repograph' / 'workspaces' / '9048503e5993' / 'repo'
print(f"Repo path: {repo}")
print(f"Exists: {repo.exists()}")
images = list(repo.rglob("*.jpg"))
print(f"Images found: {images}")
