# Graph Report - repo  (2026-09-25)

## Corpus Check
- 38 files · ~8,582 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 2 file(s) not represented in the graph (top: .example 1, .css 1)

## Summary
- 278 nodes · 584 edges · 14 communities (9 shown, 5 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 31 edges (avg confidence: 0.94)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- pipeline.py
- sessions.py
- Workspace.tsx
- chat.py
- package.json
- workspace.py
- analyzer.py
- compilerOptions
- iter_repo_files
- RepoGraph (TokenOptimizationFramework)

## God Nodes (most connected - your core abstractions)
1. `Session` - 17 edges
2. `Graph` - 16 edges
3. `_analyze_and_render()` - 16 edges
4. `WorkspaceError` - 15 edges
5. `iter_repo_files()` - 15 edges
6. `answer()` - 12 edges
7. `compilerOptions` - 11 edges
8. `render_text_pages()` - 10 edges
9. `analyze()` - 10 edges
10. `render_code_images()` - 10 edges

## Surprising Connections (you probably didn't know these)
- `create_from_url()` --uses--> `CreateSessionRequest`  [INFERRED]
  TokenOptimizationFramework/backend/src/routers/sessions.py → TokenOptimizationFramework/backend/src/schemas/api.py
- `create_from_url()` --uses--> `SessionCreated`  [INFERRED]
  TokenOptimizationFramework/backend/src/routers/sessions.py → TokenOptimizationFramework/backend/src/schemas/api.py
- `create_from_upload()` --uses--> `SessionCreated`  [INFERRED]
  TokenOptimizationFramework/backend/src/routers/sessions.py → TokenOptimizationFramework/backend/src/schemas/api.py
- `read_file()` --uses--> `FileContent`  [INFERRED]
  TokenOptimizationFramework/backend/src/routers/sessions.py → TokenOptimizationFramework/backend/src/schemas/api.py
- `build_architecture_md()` --uses--> `Graph`  [INFERRED]
  TokenOptimizationFramework/backend/src/services/architecture.py → TokenOptimizationFramework/backend/src/services/graph.py

## Import Cycles
- None detected.

## Communities (14 total, 5 thin omitted)

### Community 0 - "pipeline.py"
Cohesion: 0.07
Nodes (48): collections, dataclasses, math, pil, PixelPrompt, shutil, fit_image(), image_size() (+40 more)

### Community 1 - "sessions.py"
Cohesion: 0.08
Nodes (38): BaseModel, BaseSettings, fastapi, fastapi_middleware_cors, fastapi_responses, pydantic, pydantic_settings, starlette_datastructures (+30 more)

### Community 2 - "Workspace.tsx"
Cohesion: 0.09
Nodes (29): @monaco-editor/react, react, react-dom, api, ChatReply, ChatStats, ContextImage, json() (+21 more)

### Community 3 - "chat.py"
Cohesion: 0.09
Nodes (29): google, google_genai, hashlib, logging, Part, pathlib, estimate_image_tokens(), Gemini image cost estimate (exact numbers come back in usage_metadata). (+21 more)

### Community 4 - "package.json"
Cohesion: 0.07
Nodes (27): react-markdown, react-resizable-panels, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react, dependencies (+19 more)

### Community 5 - "workspace.py"
Cohesion: 0.18
Nodes (21): BackgroundTasks, post, Request, create_from_upload(), create_from_url(), read_file(), Render just the open file on demand (cached per path+mtime). Returns (paths,…, render_open_file() (+13 more)

### Community 6 - "analyzer.py"
Cohesion: 0.18
Nodes (17): ast, os, re, subprocess, sys, AnalysisResult, analyze(), collect_docs() (+9 more)

### Community 7 - "compilerOptions"
Cohesion: 0.15
Nodes (12): compilerOptions, isolatedModules, jsx, lib, module, moduleResolution, noEmit, skipLibCheck (+4 more)

### Community 8 - "iter_repo_files"
Cohesion: 0.39
Nodes (11): json, build_architecture_md(), detect_entry_points(), detect_frameworks(), folder_structure(), count(), walk(), Path (+3 more)

## Knowledge Gaps
- **36 isolated node(s):** `name`, `private`, `version`, `type`, `dev` (+31 more)
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 103 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `Session` connect `sessions.py` to `pipeline.py`, `chat.py`, `workspace.py`?**
  _High betweenness centrality (0.029) - this node is a cross-community bridge._
- **Why does `iter_repo_files()` connect `iter_repo_files` to `pipeline.py`, `workspace.py`, `analyzer.py`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Why does `react` connect `Workspace.tsx` to `package.json`?**
  _High betweenness centrality (0.019) - this node is a cross-community bridge._
- **Are the 9 inferred relationships involving `Session` (e.g. with `_ready()` and `_session()`) actually correct?**
  _`Session` has 9 INFERRED edges - model-reasoned connections that need verification._
- **Are the 6 inferred relationships involving `Graph` (e.g. with `build_architecture_md()` and `_importance()`) actually correct?**
  _`Graph` has 6 INFERRED edges - model-reasoned connections that need verification._
- **Are the 2 inferred relationships involving `_analyze_and_render()` (e.g. with `Graph` and `Session`) actually correct?**
  _`_analyze_and_render()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Are the 5 inferred relationships involving `WorkspaceError` (e.g. with `create_from_upload()` and `create_from_url()`) actually correct?**
  _`WorkspaceError` has 5 INFERRED edges - model-reasoned connections that need verification._