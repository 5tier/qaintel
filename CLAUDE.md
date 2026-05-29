# QAIntel

Codebase intelligence tool for QA. Indexes a git repo and exposes the knowledge base as MCP tools that Claude can query.

## Architecture

Two independent components share a JSON index on disk:

```
indexer/ (Python)  →  index/*.json  ←  mcp-server/ (TypeScript/Bun)
```

---

## Indexer

**Language:** Python 3.11+  
**Location:** `indexer/`  
**Entry point:** `python -m indexer.index`

### Run

```bash
cd /path/to/qaintel

# Full index
python -m indexer.index --repo /path/to/repo --output ./index --full

# Incremental (only changed files)
python -m indexer.index --repo /path/to/repo --output ./index --diff HEAD~1..HEAD
```

### Install dependencies

```bash
pip install -r indexer/requirements.txt
```

### Pipelines (run in parallel)

| Pipeline | Output | Tool |
|----------|--------|------|
| A – Static analysis | `symbols.json`, `callgraph.json` | tree-sitter |
| B – Embeddings | `vectors.json` | Ollama / OpenAI |
| C – LLM summaries | `summaries.json` | Anthropic / Ollama |

Also writes: `filemeta.json`, `manifest.json`, `agents_md.txt`

### Key files

| File | Purpose |
|------|---------|
| `index.py` | Entry point, orchestrates all pipelines |
| `discovery.py` | File discovery and diff filtering |
| `symbols.py` | tree-sitter symbol + callgraph extraction |
| `embeddings.py` | Chunk files and embed via Ollama/OpenAI |
| `summarize.py` | LLM file summaries |
| `git_meta.py` | Git blame / log metadata |
| `output.py` | Write index JSON files to disk |
| `config.py` | Env var config |
| `models.py` | Pydantic models |

---

## MCP Server

**Language:** TypeScript  
**Runtime:** Bun  
**Location:** `mcp-server/`

### Run

```bash
cd mcp-server

bun install          # first time
bun run src/server.ts          # production
bun --watch src/server.ts      # dev (auto-reload)
```

Default port: **3000**

### Key files

| File | Purpose |
|------|---------|
| `server.ts` | Express app, routes, startup |
| `mcp.ts` | MCP protocol handling |
| `tools.ts` | Tool schemas (add new tools here) |
| `handlers.ts` | Tool implementations (add matching cases here) |
| `index-store.ts` | Loads and serves the JSON index |
| `embed.ts` | Embedding calls for `search_code` |
| `auth.ts` | Bearer token middleware |
| `config.ts` | Env var config |

### Exposed MCP tools

`get_symbol` · `search_code` · `get_file_summary` · `explain_impact` · `get_feature_history` · `get_test_targets` · `list_routes` · `get_coverage_gaps` · `get_churn_report` · `get_conventions` · `get_recent_changes`

To add a tool: define schema in `tools.ts`, add handler `case` in `handlers.ts`.

---

## Environment Variables

Copy `.env.example` → `.env`. Key vars:

### Embedding model (`EMBED_*`)

| Variable | Default | Notes |
|----------|---------|-------|
| `EMBED_PROVIDER` | `ollama` | `ollama` or `openai` (covers any OpenAI-compatible endpoint) |
| `EMBED_MODEL` | `qwen3-embedding:4b` | Model name for the chosen provider |
| `EMBED_BASE_URL` | `http://localhost:11434` (ollama) / `https://api.openai.com/v1` (openai) | Custom endpoint (LM Studio, vLLM, Azure, etc.) |
| `EMBED_API_KEY` | `""` | API key for the chosen provider |

### Summary model (`SUMMARY_*`)

| Variable | Default | Notes |
|----------|---------|-------|
| `SUMMARY_PROVIDER` | `ollama` | `ollama`, `openai`, or `anthropic` |
| `SUMMARY_MODEL` | `minimax-m2.7:cloud` | Model name for the chosen provider |
| `SUMMARY_BASE_URL` | provider default | Custom endpoint |
| `SUMMARY_API_KEY` | `""` | API key for the chosen provider |

### Indexer & MCP server

| Variable | Default | Used by |
|----------|---------|---------|
| `REPO_PATH` | — | indexer |
| `OUTPUT_PATH` | `./index` | indexer |
| `MAX_FILE_SIZE` | `100000` | indexer |
| `CHUNK_SIZE` | `400` | indexer |
| `CHUNK_OVERLAP` | `80` | indexer |
| `INDEX_PATH` | `./index` | mcp-server |
| `PORT` | `3000` | mcp-server |
| `MCP_API_TOKEN` | `dev-token` | mcp-server |
| `INTERNAL_TOKEN` | — | mcp-server (hot-reload) |

> **Legacy vars** (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `EMBEDDING_MODEL`, `OLLAMA_HOST`, etc.) still work as automatic fallbacks — existing `.env` files do not need updating.

---

## Docker

Multi-stage build: `base → server → indexed → final`

```bash
docker build \
  --build-arg REPO_URL=https://github.com/org/repo \
  --build-arg REPO_TOKEN=ghp_xxx \
  --build-arg ANTHROPIC_API_KEY=sk-ant-xxx \
  -t qaintel .

docker run -p 3000:3000 qaintel
```

The `indexed` stage clones the repo, runs the indexer, and bakes the index into the image. The `final` stage serves it via the MCP server.

---

## Conventions

- **Indexer:** async-first (`asyncio`). Pipelines B and C always run with `asyncio.gather`.
- **MCP server:** add tool schema in `tools.ts` and a matching handler branch in `handlers.ts` — keep them in sync.
- No test framework configured yet; check `AGENTS.md` in the target repo for project-specific conventions.
