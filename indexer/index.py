#!/usr/bin/env python3
"""
QAIntel Indexer

Builds the knowledge base from a git repository.
Runs three pipelines in parallel:
  A. Static analysis  → symbols.json, callgraph.json
  B. Embedding        → vectors.json
  C. LLM summarize    → summaries.json

Usage:
  python -m indexer.index --repo /path/to/repo --output /index --full
  python -m indexer.index --repo /path/to/repo --output /index --diff HEAD~1..HEAD

Requirements:
  pip install tree-sitter tree-sitter-languages gitpython aiohttp asyncio

Environment variables (optional):
  OLLAMA_HOST        — local Ollama URL for embeddings  (default: http://localhost:11434)
  OLLAMA_CLOUD_HOST  — Ollama URL for LLM summaries     (default: http://localhost:11434)
"""

import asyncio
import argparse
from pathlib import Path

from .discovery  import discover_files, diff_files
from .symbols    import extract_symbols
from .git_meta   import extract_file_meta, build_manifest
from .embeddings import chunk_file, embed_chunks
from .summarize  import summarize_files
from .output     import write_index


def _branch_slug(branch: str) -> str:
    """Convert a branch name to a safe directory name, e.g. feature/payments → feature-payments."""
    return branch.replace('/', '-').replace(' ', '_').strip('-')


async def main():
    args = _parse_args()

    repo_path   = Path(args.repo).resolve()
    output_path = Path(args.output).resolve()

    # If --branch is given, write the index into a named subdirectory so
    # multiple branches can coexist under the same output root.
    branch_override = args.branch or None  # str or None
    if branch_override:
        output_path = output_path / _branch_slug(branch_override)

    print(f"[indexer] Repo:   {repo_path}")
    print(f"[indexer] Output: {output_path}")
    print(f"[indexer] Branch: {branch_override or '(from git HEAD)'}")
    print(f"[indexer] Mode:   {'full' if args.full else 'diff: ' + args.diff}")

    # ── File discovery ────────────────────────────────────────────────────────
    if args.diff:
        files = diff_files(repo_path, args.diff)
        print(f"[indexer] Changed files: {len(files)}")
    else:
        files = discover_files(repo_path)
        print(f"[indexer] Total files: {len(files)}")

    agents_md_path = repo_path / 'AGENTS.md'
    agents_md      = agents_md_path.read_text() if agents_md_path.exists() else '# No AGENTS.md'

    # ── Pipeline A: static analysis (sync, fast) ──────────────────────────────
    print("\n[A] Running static analysis...")
    symbols, callgraph = extract_symbols(files, repo_path)
    print(f"[A] Found {len(symbols)} symbols across {len(callgraph)} files")

    # ── Git metadata (sync) ───────────────────────────────────────────────────
    print("\n[git] Extracting file metadata...")
    filemeta = extract_file_meta(files, repo_path)

    # ── Pipeline B + C: embeddings + LLM summaries (parallel, async) ─────────
    print("\n[B+C] Running embedding + summarization pipelines...")
    chunks = []
    for file in files:
        rel = str(file.relative_to(repo_path))
        chunks.extend(chunk_file(file, rel))
    print(f"[B] Total chunks: {len(chunks)}")

    vectors, summaries = await asyncio.gather(
        embed_chunks(chunks),
        summarize_files(files, repo_path),
    )
    print(f"[B] Vectors: {len(vectors)}")
    print(f"[C] Summaries: {len(summaries)}")

    # ── Write output ──────────────────────────────────────────────────────────
    manifest = build_manifest(repo_path, len(files), branch_override=branch_override)
    print("\n[write] Writing index...")
    write_index(output_path, symbols, callgraph, summaries, vectors, filemeta, manifest, agents_md)

    print(f"\n[done] Index built — sha={manifest['sha']} · {len(files)} files · {len(symbols)} symbols")


def _parse_args():
    parser = argparse.ArgumentParser(description='QAIntel Indexer')
    parser.add_argument('--repo',   required=True, help='Path to git repo')
    parser.add_argument('--output', required=True, help='Output root directory (index written to OUTPUT/branch-slug/ when --branch is given)')
    parser.add_argument('--branch', default='',    help='Branch name — index stored at OUTPUT/<slug>/. Defaults to current HEAD branch.')
    parser.add_argument('--full',   action='store_true', help='Full reindex')
    parser.add_argument('--diff',   help='Only index files changed in this range, e.g. HEAD~1..HEAD')
    return parser.parse_args()


if __name__ == '__main__':
    asyncio.run(main())
