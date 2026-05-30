from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path


def extract_file_meta(files: list[Path], repo_path: Path) -> dict:
    meta = {}
    for file_path in files:
        rel = str(file_path.relative_to(repo_path))
        commits = _commit_log(repo_path, rel)
        meta[rel] = {
            "lines": _line_count(file_path),
            "commits": len(commits),
            "authors": sorted({item["author"] for item in commits}),
            "last_changed": commits[0]["date"] if commits else None,
            "created_at": commits[-1]["date"] if commits else None,
            "created_by": commits[-1]["author"] if commits else None,
            "created_message": commits[-1]["message"] if commits else None,
            "commit_log": commits[:20],
        }
    return meta


def build_manifest(repo_path: Path, file_count: int, branch_override: str | None = None) -> dict:
    sha = _run_git(repo_path, ["rev-parse", "HEAD"])
    branch = branch_override or _current_branch(repo_path)
    return {
        "sha": sha,
        "branch": branch,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "file_count": file_count,
    }


def _line_count(file_path: Path) -> int:
    try:
        return len(file_path.read_text(errors="ignore").splitlines())
    except OSError:
        return 0


def _commit_log(repo_path: Path, rel_path: str) -> list[dict]:
    output = _run_git(
        repo_path,
        ["log", "--follow", "--format=%cI%x1f%an%x1f%s", "--", rel_path],
        allow_empty=True,
    )
    commits = []
    for line in output.splitlines():
        parts = line.split("\x1f", 2)
        if len(parts) == 3:
            commits.append({"date": parts[0], "author": parts[1], "message": parts[2]})
    return commits


def _current_branch(repo_path: Path) -> str:
    branch = _run_git(repo_path, ["rev-parse", "--abbrev-ref", "HEAD"], allow_empty=True)
    return branch if branch and branch != "HEAD" else "detached"


def _run_git(repo_path: Path, args: list[str], allow_empty: bool = False) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and not allow_empty:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout.strip()
