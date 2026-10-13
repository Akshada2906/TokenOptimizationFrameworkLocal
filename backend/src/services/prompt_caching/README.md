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

## PixelPrompt image-cache benchmark

This companion benchmark extracts each PDF page, renders it as a separate PixelPrompt PNG,
then compares sending all PNGs on every request with reusing the same PNG set through one
Gemini explicit cache:

```bat
uv run python -m src.services.prompt_caching.image_cache_benchmark --claims 3
```

To generate and inspect the images without making Gemini API calls:

```bat
uv run python -m src.services.prompt_caching.image_cache_benchmark --prepare-only --regenerate-images
```

Generated PNGs and reports are written below `backend/artifacts/prompt_caching/` and ignored
by Git. PixelPrompt receives extracted text, so this benchmark measures text rendered as images;
it does not preserve diagrams or other graphics from an arbitrary source PDF.

## Hybrid 100-page web POC

The web POC at `http://localhost:5173/prompt-caching` uses the bundled synthetic document:

```text
data/Employee_Expense_Policy_POC_100p.pdf
```

Its preprocessing pipeline is implemented in `hybrid_policy.py`:

1. PyMuPDF reads text blocks and native page geometry.
2. pdfplumber extracts tables, which are converted to Markdown and rendered by PixelPrompt.
3. Prose is rendered by PixelPrompt, while substantial non-table vector/raster regions are
   cropped directly from the PDF.
4. Every item is sorted by PDF page, vertical position, and item number before being cached.

The same cache supports free-form policy questions and structured claim classification. The
browser shows cached tokens, fresh input tokens, output tokens, and answer latency. When the
remote Gemini cache reaches its TTL, the backend rebuilds it from the saved ordered images and
retries the request; the PDF is not reparsed.

Run the API and UI from separate terminals:

```bat
cd backend
set "PYTHONPATH=%CD%"
..\.venv\Scripts\python.exe -m uvicorn src.main:app --reload
```

```bat
cd frontend
npm run dev
```
