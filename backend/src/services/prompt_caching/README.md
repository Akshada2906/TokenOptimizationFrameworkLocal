# Expense Policy Prompt-Caching POC

This standalone benchmark compares a full expense-policy prompt on every Gemini request with Gemini explicit context caching. It does not use PixelPrompt or modify the repository-chat API. Its default source is an inspectable, selectable-text 19-page synthetic expense-policy PDF.

## Run

From `backend` in the environment that has `google-genai` and the backend requirements installed:

```bat
set "PYTHONPATH=%CD%;%CD%\.."
uv run python -m src.services.prompt_caching.benchmark
```

Set `GEMINI_API_KEY` in `backend/.env`. Optionally select a cache-capable model:

```text
EXPENSE_CACHE_MODEL=your-cache-capable-gemini-model
EXPENSE_CACHE_TTL_SECONDS=3600
```

The policy consists of the core `data/expense_policy.md` plus generated, deterministic destination allowance and decision-example appendices. The run calls Gemini token counting first and writes JSON and Markdown reports under `backend/artifacts/prompt_caching/`.

On the first run, it generates this source document:

```text
backend/artifacts/prompt_caching/source_data/expense_policy_fy2026.pdf
```

The POC extracts text from the PDF before placing it in Gemini's cache. This is intentional: it evaluates reusable **policy text** rather than image or PDF-vision tokens. Use another selectable-text PDF with `--source-pdf "C:\path\to\policy.pdf"`; scanned PDFs need OCR before they can be used.

The cache is deleted after the run by default. Use `--keep-cache` only when you deliberately want to test reuse across separate runs; storage can continue until its TTL expires or you delete it.
