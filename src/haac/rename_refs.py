"""Scan and rewrite references across the repo when an HA ID is renamed."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

from haac.git_ctx import GitContext


@dataclass
class RefHit:
    path: Path         # relative to repo root
    line_number: int
    line: str


_BINARY_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".pdf", ".zip", ".tar", ".gz"}
_SKIP_FILES = {"haac.yaml"}


def _token_regex(needle: str) -> re.Pattern:
    return re.compile(rf"(?<!\w){re.escape(needle)}(?!\w)")


def _is_scannable(path: Path) -> bool:
    if path.name in _SKIP_FILES:
        return False
    if path.suffix in _BINARY_EXTENSIONS:
        return False
    return True


def scan_references(git_ctx: GitContext, needle: str) -> list[RefHit]:
    """Find whole-token matches of `needle` across all tracked/untracked files."""
    if not git_ctx.is_repo():
        return []
    pattern = _token_regex(needle)
    hits: list[RefHit] = []
    for rel in git_ctx.ls_files():
        if not _is_scannable(rel):
            continue
        full = git_ctx.root / rel
        if not full.is_file():
            continue
        try:
            content = full.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        for i, line in enumerate(content.splitlines(), start=1):
            if pattern.search(line):
                hits.append(RefHit(path=rel, line_number=i, line=line))
    return hits


def rewrite_references(git_ctx: GitContext, old: str, new: str) -> list[Path]:
    """Replace whole-token occurrences of `old` with `new` across the repo.

    Pre-checks that all candidate files are writable before modifying any.
    On any write failure, restores via git checkout. Returns list of paths changed.
    """
    pattern = _token_regex(old)
    hits = scan_references(git_ctx, old)
    files_to_write: list[tuple[Path, Path, str]] = []

    seen_paths: set[Path] = set()
    for hit in hits:
        if hit.path in seen_paths:
            continue
        seen_paths.add(hit.path)
        full = git_ctx.root / hit.path
        try:
            content = full.read_text()
        except (UnicodeDecodeError, OSError):
            continue
        updated = pattern.sub(new, content)
        if updated != content:
            files_to_write.append((full, hit.path, updated))

    # Pre-check writability
    for full, _rel, _content in files_to_write:
        if not full.is_file() or not os.access(full, os.W_OK):
            raise PermissionError(f"not writable: {full}")

    # Write all
    written_rel: list[Path] = []
    try:
        for full, rel, content in files_to_write:
            full.write_text(content)
            written_rel.append(rel)
    except Exception:
        if written_rel:
            git_ctx.checkout(written_rel)
        raise

    return written_rel
