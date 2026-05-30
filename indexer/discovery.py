from __future__ import annotations

import subprocess
from pathlib import Path

from .config import IGNORE_DIRS, MAX_FILE_SIZE, SUPPORTED_EXTENSIONS


def discover_files(repo_path: Path) -> list[Path]:
    _ensure_repo_path(repo_path)
    files = [path for path in repo_path.rglob("*") if _is_indexable(path, repo_path)]
    return sorted(files, key=lambda path: str(path.relative_to(repo_path)))


def diff_files(repo_path: Path, diff_range: str) -> list[Path]:
    _ensure_repo_path(repo_path)
    result = _run_git(repo_path, ["diff", "--name-only", diff_range])
    files = []
    for line in result.splitlines():
        path = (repo_path / line.strip()).resolve()
        if _is_indexable(path, repo_path):
            files.append(path)
    return sorted(files, key=lambda path: str(path.relative_to(repo_path)))


def _ensure_repo_path(repo_path: Path) -> None:
    if not repo_path.exists() or not repo_path.is_dir():
        raise ValueError(f"Repo path does not exist or is not a directory: {repo_path}")
    _run_git(repo_path, ["rev-parse", "--is-inside-work-tree"])


def _is_indexable(path: Path, repo_path: Path) -> bool:
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        return False
    try:
        rel_parts = path.relative_to(repo_path).parts
    except ValueError:
        return False
    if any(part in IGNORE_DIRS for part in rel_parts):
        return False
    return path.stat().st_size <= MAX_FILE_SIZE


def _run_git(repo_path: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()
