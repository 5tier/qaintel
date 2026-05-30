from __future__ import annotations

import asyncio
from pathlib import Path

import aiohttp

from .config import CHUNK_OVERLAP, CHUNK_SIZE, EMBED_CONFIG

MAX_CONCURRENT_EMBEDDINGS = 8


def chunk_file(file: Path, rel_path: str) -> list[dict]:
    text = file.read_text(errors="ignore")
    lines = text.splitlines()
    if not lines:
        return []

    chunks = []
    step = max(1, CHUNK_SIZE - CHUNK_OVERLAP)
    for start in range(0, len(lines), step):
        part = lines[start : start + CHUNK_SIZE]
        if not part:
            continue
        chunks.append(
            {
                "file": rel_path,
                "text": "\n".join(part),
                "start_line": start + 1,
                "end_line": start + len(part),
            }
        )
    return chunks


async def embed_chunks(chunks: list[dict]) -> list[dict]:
    if not chunks:
        return []
    if EMBED_CONFIG.provider == "ollama":
        return await _embed_ollama(chunks)
    if EMBED_CONFIG.provider == "openai":
        return await _embed_openai(chunks)
    raise RuntimeError(f"Unsupported embedding provider: {EMBED_CONFIG.provider}")


async def _embed_ollama(chunks: list[dict]) -> list[dict]:
    url = f"{EMBED_CONFIG.base_url.rstrip('/')}/api/embeddings"
    timeout = aiohttp.ClientTimeout(total=120)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_EMBEDDINGS)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [_embed_ollama_chunk(session, url, chunk, semaphore) for chunk in chunks]
        return await asyncio.gather(*tasks)


async def _embed_ollama_chunk(
    session: aiohttp.ClientSession,
    url: str,
    chunk: dict,
    semaphore: asyncio.Semaphore,
) -> dict:
    payload = {"model": EMBED_CONFIG.model, "prompt": chunk["text"]}
    async with semaphore:
        data = await _post_json(session, url, payload, _auth_headers())
    vector = data.get("embedding")
    if not isinstance(vector, list):
        raise RuntimeError("Ollama embedding response did not include an embedding array")
    return _vector_entry(chunk, vector)


async def _embed_openai(chunks: list[dict]) -> list[dict]:
    if not EMBED_CONFIG.api_key:
        raise RuntimeError("OpenAI embeddings require EMBED_API_KEY or OPENAI_API_KEY")

    url = f"{EMBED_CONFIG.base_url.rstrip('/')}/embeddings"
    payload = {"model": EMBED_CONFIG.model, "input": [chunk["text"] for chunk in chunks]}
    timeout = aiohttp.ClientTimeout(total=120)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        data = await _post_json(session, url, payload, _auth_headers())

    items = sorted(data.get("data", []), key=lambda item: item.get("index", 0))
    if len(items) != len(chunks):
        raise RuntimeError("OpenAI embedding response count did not match chunk count")
    return [_vector_entry(chunk, item.get("embedding")) for chunk, item in zip(chunks, items)]


async def _post_json(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict,
    headers: dict,
) -> dict:
    try:
        async with session.post(url, json=payload, headers=headers) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"Embedding provider failed: HTTP {response.status}: {text[:500]}")
            return await response.json()
    except aiohttp.ClientError as exc:
        raise RuntimeError(f"Embedding provider is unreachable at {url}: {exc}") from exc


def _auth_headers() -> dict:
    if not EMBED_CONFIG.api_key:
        return {}
    return {"Authorization": f"Bearer {EMBED_CONFIG.api_key}"}


def _vector_entry(chunk: dict, vector: list[float] | None) -> dict:
    if not isinstance(vector, list):
        raise RuntimeError(f"Embedding provider returned an invalid vector for {chunk['file']}")
    return {
        "file": chunk["file"],
        "text": chunk["text"],
        "vector": vector,
        "start_line": chunk["start_line"],
        "end_line": chunk["end_line"],
    }
