"""Wrapper around git subprocess calls — single seam for all git access."""

import subprocess
from pathlib import Path


class GitContext:
    """Lightweight git wrapper rooted at a repo directory.

    Methods return None / False on non-git directories or missing HEAD
    rather than raising — callers decide whether the absence is an error.
    """

    def __init__(self, repo_root: Path):
        self.root = repo_root

    def is_repo(self) -> bool:
        result = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _has_head(self) -> bool:
        result = subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "--verify", "HEAD"],
            capture_output=True, text=True,
        )
        return result.returncode == 0

    def head_blob(self, relative_path: Path) -> str | None:
        """Return contents of `relative_path` at HEAD, or None if unavailable."""
        if not self.is_repo() or not self._has_head():
            return None
        result = subprocess.run(
            ["git", "-C", str(self.root), "show", f"HEAD:{relative_path.as_posix()}"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout

    def ls_files(self) -> list[Path]:
        """Tracked + untracked files, respecting .gitignore."""
        if not self.is_repo():
            return []
        result = subprocess.run(
            ["git", "-C", str(self.root), "ls-files", "--cached", "--others", "--exclude-standard"],
            capture_output=True, text=True, check=True,
        )
        return [Path(line) for line in result.stdout.splitlines() if line]

    def add(self, paths: list[Path]) -> None:
        if not paths:
            return
        subprocess.run(
            ["git", "-C", str(self.root), "add", "--", *(p.as_posix() for p in paths)],
            check=True,
        )

    def commit(self, message: str) -> None:
        subprocess.run(
            ["git", "-C", str(self.root), "commit", "-m", message],
            check=True,
        )

    def differs_from_head(self, relative_path: Path) -> bool:
        """True if working-tree contents differ from HEAD (new files count)."""
        if not self.is_repo():
            return False
        result = subprocess.run(
            ["git", "-C", str(self.root), "status", "--porcelain", "--", relative_path.as_posix()],
            capture_output=True, text=True,
        )
        return bool(result.stdout.strip())

    def checkout(self, paths: list[Path]) -> None:
        """Revert paths to HEAD — used to roll back failed rewrites."""
        if not paths:
            return
        subprocess.run(
            ["git", "-C", str(self.root), "checkout", "--", *(p.as_posix() for p in paths)],
            check=True,
        )
