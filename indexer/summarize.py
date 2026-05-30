from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from .config import MAX_FILE_SIZE, SUMMARY_CONFIG

MAX_SUMMARY_CHARS = 12_000
MAX_CONCURRENT_SUMMARIES = 4


async def summarize_files(files: list[Path], repo_path: Path) -> dict:
    if not files:
        return {}

    timeout = aiohttp.ClientTimeout(total=180)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SUMMARIES)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        tasks = [_summarize_one(session, file, repo_path, semaphore) for file in files]
        pairs = await asyncio.gather(*tasks)
    return {rel: summary for rel, summary in sorted(pairs)}


async def _summarize_one(
    session: aiohttp.ClientSession,
    file: Path,
    repo_path: Path,
    semaphore: asyncio.Semaphore,
) -> tuple[str, dict]:
    rel = str(file.relative_to(repo_path))
    if file.stat().st_size > MAX_FILE_SIZE:
        raise RuntimeError(f"Summary skipped oversized file unexpectedly: {rel}")

    content = file.read_text(errors="ignore")[:MAX_SUMMARY_CHARS]
    prompt = _summary_prompt(rel, content)
    async with semaphore:
        text = await _call_summary_provider(session, prompt)
    summary = _parse_summary(text)
    summary["changed_at"] = datetime.fromtimestamp(file.stat().st_mtime, timezone.utc).isoformat()
    return rel, summary


async def _call_summary_provider(session: aiohttp.ClientSession, prompt: str) -> str:
    provider = SUMMARY_CONFIG.provider
    if provider == "ollama":
        return await _call_ollama(session, prompt)
    if provider == "openai":
        return await _call_openai(session, prompt)
    if provider == "anthropic":
        return await _call_anthropic(session, prompt)
    raise RuntimeError(f"Unsupported summary provider: {provider}")


async def _call_ollama(session: aiohttp.ClientSession, prompt: str) -> str:
    url = f"{SUMMARY_CONFIG.base_url.rstrip('/')}/api/generate"
    data = await _post_json(
        session,
        url,
        {"model": SUMMARY_CONFIG.model, "prompt": prompt, "stream": False},
        _auth_headers(),
        "Summary provider",
    )
    return data.get("response", "")


async def _call_openai(session: aiohttp.ClientSession, prompt: str) -> str:
    if not SUMMARY_CONFIG.api_key:
        raise RuntimeError("OpenAI summaries require SUMMARY_API_KEY or OPENAI_API_KEY")
    url = f"{SUMMARY_CONFIG.base_url.rstrip('/')}/chat/completions"
    data = await _post_json(
        session,
        url,
        {
            "model": SUMMARY_CONFIG.model,
            "temperature": 0.2,
            "messages": [{"role": "user", "content": prompt}],
        },
        _auth_headers(),
        "Summary provider",
    )
    return data["choices"][0]["message"]["content"]


async def _call_anthropic(session: aiohttp.ClientSession, prompt: str) -> str:
    if not SUMMARY_CONFIG.api_key:
        raise RuntimeError("Anthropic summaries require SUMMARY_API_KEY or ANTHROPIC_API_KEY")
    url = f"{SUMMARY_CONFIG.base_url.rstrip('/')}/v1/messages"
    data = await _post_json(
        session,
        url,
        {
            "model": SUMMARY_CONFIG.model,
            "max_tokens": 500,
            "messages": [{"role": "user", "content": prompt}],
        },
        {
            "x-api-key": SUMMARY_CONFIG.api_key,
            "anthropic-version": "2023-06-01",
        },
        "Summary provider",
    )
    return "\n".join(part.get("text", "") for part in data.get("content", []) if part.get("type") == "text")


async def _post_json(
    session: aiohttp.ClientSession,
    url: str,
    payload: dict,
    headers: dict,
    label: str,
) -> dict:
    try:
        async with session.post(url, json=payload, headers=headers) as response:
            text = await response.text()
            if response.status >= 400:
                raise RuntimeError(f"{label} failed: HTTP {response.status}: {text[:500]}")
            return await response.json()
    except aiohttp.ClientError as exc:
        raise RuntimeError(f"{label} is unreachable at {url}: {exc}") from exc


def _auth_headers() -> dict:
    if not SUMMARY_CONFIG.api_key:
        return {}
    return {"Authorization": f"Bearer {SUMMARY_CONFIG.api_key}"}


def _summary_prompt(rel: str, content: str) -> str:
    return f"""Summarize this source file for a code intelligence index.
Return only compact JSON with keys: summary, exports, risks, test_hint.
Use exports as an array of names.

File: {rel}
```text
{content}
```"""


def _parse_summary(text: str) -> dict:
    parsed = _extract_json(text)
    return {
        "summary": str(parsed.get("summary", "")).strip(),
        "exports": _string_list(parsed.get("exports", [])),
        "risks": str(parsed.get("risks", "")).strip(),
        "test_hint": str(parsed.get("test_hint", "")).strip(),
    }


def _extract_json(text: str) -> dict:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        raise RuntimeError(f"Summary provider returned non-JSON output: {text[:300]}")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Summary provider returned malformed JSON: {exc}") from exc


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value:
        return [value]
    return []
