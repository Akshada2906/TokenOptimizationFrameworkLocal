"""Decide what context a question needs.

The code-review graph images (graph, wiki, architecture) are the grounding for every question.
An open file is added on top of them, rendered fresh, so answers about a file can still refer to
the graph (callers, imports, neighbours).
"""


def classify(message: str, open_file: str | None) -> str:
    """Returns 'structural' (graph images only) or 'both' (graph images + the open file's images)."""
    return "both" if open_file else "structural"
