from __future__ import annotations

import hashlib
import platform
import subprocess
from pathlib import Path

from antenna_ingest.orchestration.schemas import RunFingerprint


def collect_run_fingerprint(start: Path | None = None) -> RunFingerprint:
    repository_root = find_repository_root(start)
    git_commit = _git_value(repository_root, ["rev-parse", "HEAD"])
    git_status = _git_value(repository_root, ["status", "--porcelain"])
    return RunFingerprint(
        git_commit=git_commit,
        git_dirty=None if git_status is None else bool(git_status),
        python_version=platform.python_version(),
        platform=platform.platform(),
        pyproject_sha256=_optional_checksum(repository_root / "pyproject.toml"),
        lockfile_sha256=_optional_checksum(repository_root / "uv.lock"),
    )


def find_repository_root(start: Path | None = None) -> Path:
    search_starts = [Path(start or Path.cwd()).resolve(), Path(__file__).resolve()]
    for search_start in search_starts:
        current = search_start if search_start.is_dir() else search_start.parent
        for candidate in (current, *current.parents):
            if (candidate / "pyproject.toml").is_file():
                return candidate
    return Path(start or Path.cwd()).resolve()


def _git_value(repository_root: Path, arguments: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *arguments],
            cwd=repository_root,
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip()


def _optional_checksum(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
