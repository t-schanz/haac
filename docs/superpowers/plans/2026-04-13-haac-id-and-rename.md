# `haac_id` and Rename Support — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every managed YAML entry a stable `haac_id` UUID, use git HEAD to detect HA-ID renames on plan/apply, rewrite references across the repo interactively, and prompt for a scoped auto-commit after apply.

**Architecture:** A new `GitContext` wraps all subprocess calls to git. Each provider's `pull` backfills `haac_id` on fresh entries; `read_desired` carries it through; `diff` keys matching on HA ID but falls back to `git_head_entry(haac_id)` for rename detection, emitting a new `Change(action="rename")`. Auto-rename scans tracked files with a whole-token regex, prompts, rewrites, re-plans. Apply tracks touched paths and prompts for a scoped `git commit`.

**Tech Stack:** Python 3.12, PyYAML, Rich, pytest, pytest-asyncio, `subprocess` for git

**Spec:** `docs/superpowers/specs/2026-04-13-haac-id-and-rename-design.md`

---

## Phases

- **Phase A** (Tasks 1–6): `haac_id` backfill across all providers. Ships alone — no user-visible change beyond the new field in YAML.
- **Phase B** (Tasks 7–13): Rename detection, `Change.rename`, per-provider rename API calls, plan output.
- **Phase C** (Tasks 14–16): Interactive reference rewriting with re-plan.
- **Phase D** (Tasks 17–19): Auto-commit after apply + CLI flags.

Each phase commits cleanly and leaves the tree green.

---

## File Structure

| File | Role |
|------|------|
| `src/haac/git_ctx.py` | **new** — `GitContext` class wrapping git subprocess calls |
| `src/haac/models.py` | Add `"rename"` to `Change.action` values; document in docstring |
| `src/haac/providers/__init__.py` | Add `_ensure_haac_id()`, `git_head_entry()`; update base `pull()` to backfill; update `parse_state_file()` to allow `haac_id` |
| `src/haac/providers/floors.py` | Match on `haac_id`, emit rename, apply rename via `config/floor_registry/update` |
| `src/haac/providers/labels.py` | Same shape as floors |
| `src/haac/providers/areas.py` | Same shape as floors |
| `src/haac/providers/entities.py` | Custom `pull` backfills `haac_id`; `diff` emits rename; `apply_change` sends `new_entity_id` |
| `src/haac/providers/helpers.py` | Same shape as floors |
| `src/haac/providers/automations.py` | Rename via POST-new + DELETE-old |
| `src/haac/providers/scenes.py` | Same as automations |
| `src/haac/providers/dashboard.py` | Skip rename (single resource); preserve `haac_id` if present |
| `src/haac/output.py` | Render rename action in `print_plan` + `print_apply_change` |
| `src/haac/rename_refs.py` | **new** — scan + preview + rewrite references across repo |
| `src/haac/cli.py` | Add flags, wire up rename-refs prompt, wire up auto-commit prompt |
| `tests/test_git_ctx.py` | **new** — tempdir git repo fixture, GitContext tests |
| `tests/test_haac_id_backfill.py` | **new** — pull assigns UUIDs; idempotent; preserves existing |
| `tests/test_rename_detection.py` | **new** — per-provider rename detection via git |
| `tests/test_rename_refs.py` | **new** — repo-wide scan + rewrite |
| `tests/test_auto_commit.py` | **new** — scoped add, prompt flows |

---

## Phase A — `haac_id` backfill

### Task 1: `GitContext` module

**Files:**
- Create: `src/haac/git_ctx.py`
- Create: `tests/test_git_ctx.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_git_ctx.py`:

```python
"""Tests for GitContext."""
import subprocess
from pathlib import Path

import pytest

from haac.git_ctx import GitContext


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit(repo: Path, path: str, content: str, msg: str = "x") -> None:
    (repo / path).parent.mkdir(parents=True, exist_ok=True)
    (repo / path).write_text(content)
    subprocess.run(["git", "add", path], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=repo, check=True)


def test_is_repo_true(git_repo):
    assert GitContext(git_repo).is_repo() is True


def test_is_repo_false(tmp_path):
    assert GitContext(tmp_path).is_repo() is False


def test_head_blob_returns_content(git_repo):
    _commit(git_repo, "state/x.yaml", "hello\n")
    assert GitContext(git_repo).head_blob(Path("state/x.yaml")) == "hello\n"


def test_head_blob_returns_none_for_untracked(git_repo):
    _commit(git_repo, "seed.txt", "x")
    assert GitContext(git_repo).head_blob(Path("state/missing.yaml")) is None


def test_head_blob_returns_none_when_no_head(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    assert GitContext(tmp_path).head_blob(Path("anything.yaml")) is None


def test_ls_files_respects_gitignore(git_repo):
    _commit(git_repo, ".gitignore", "ignored.yaml\n")
    _commit(git_repo, "tracked.yaml", "x")
    (git_repo / "ignored.yaml").write_text("y")
    (git_repo / "untracked.yaml").write_text("z")
    files = {p.as_posix() for p in GitContext(git_repo).ls_files()}
    assert "tracked.yaml" in files
    assert "ignored.yaml" not in files
    # untracked-but-not-ignored files DO appear in ls_files with --others
    assert "untracked.yaml" in files


def test_add_and_commit(git_repo):
    _commit(git_repo, "seed.txt", "x")
    new_file = git_repo / "new.yaml"
    new_file.write_text("content")
    ctx = GitContext(git_repo)
    ctx.add([Path("new.yaml")])
    ctx.commit("test: add new.yaml")
    log = subprocess.run(
        ["git", "log", "--oneline"], cwd=git_repo, capture_output=True, text=True, check=True
    ).stdout
    assert "test: add new.yaml" in log


def test_changed_vs_head(git_repo):
    _commit(git_repo, "a.yaml", "orig\n")
    (git_repo / "a.yaml").write_text("modified\n")
    ctx = GitContext(git_repo)
    assert ctx.differs_from_head(Path("a.yaml")) is True
    assert ctx.differs_from_head(Path("nonexistent.yaml")) is False
```

- [ ] **Step 2: Run the test to verify failure**

Run: `uv run pytest tests/test_git_ctx.py -v`
Expected: FAIL — `ModuleNotFoundError: haac.git_ctx`

- [ ] **Step 3: Implement `GitContext`**

Create `src/haac/git_ctx.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_git_ctx.py -v`
Expected: PASS (all 8 tests)

- [ ] **Step 5: Commit**

```bash
git add src/haac/git_ctx.py tests/test_git_ctx.py
git commit -m "feat: add GitContext wrapper for git subprocess calls"
```

---

### Task 2: `haac_id` helpers in providers module

**Files:**
- Modify: `src/haac/providers/__init__.py`
- Create: `tests/test_haac_id_backfill.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_haac_id_backfill.py`:

```python
"""Tests for haac_id backfill and identity helpers."""
import re
import uuid

from haac.providers import _ensure_haac_id


UUID_RE = re.compile(r"^[0-9a-f-]{36}$")


def test_ensure_haac_id_adds_when_missing():
    entries = [{"name": "Ground"}]
    _ensure_haac_id(entries)
    assert "haac_id" in entries[0]
    assert UUID_RE.match(entries[0]["haac_id"])


def test_ensure_haac_id_preserves_existing():
    existing = str(uuid.uuid4())
    entries = [{"haac_id": existing, "name": "Ground"}]
    _ensure_haac_id(entries)
    assert entries[0]["haac_id"] == existing


def test_ensure_haac_id_assigns_unique_ids():
    entries = [{"name": "A"}, {"name": "B"}, {"name": "C"}]
    _ensure_haac_id(entries)
    ids = {e["haac_id"] for e in entries}
    assert len(ids) == 3


def test_ensure_haac_id_moves_field_to_front():
    entries = [{"name": "A", "icon": "x"}]
    _ensure_haac_id(entries)
    assert list(entries[0].keys())[0] == "haac_id"
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_haac_id_backfill.py -v`
Expected: FAIL — `ImportError: cannot import name '_ensure_haac_id'`

- [ ] **Step 3: Implement `_ensure_haac_id`**

In `src/haac/providers/__init__.py`, add near the top (after imports):

```python
import uuid


def _ensure_haac_id(entries: list[dict]) -> None:
    """In-place: assign haac_id to any entry missing one, move to first key."""
    for i, entry in enumerate(entries):
        if "haac_id" not in entry:
            entry["haac_id"] = str(uuid.uuid4())
        # Reorder so haac_id is first key for readability
        if list(entry.keys())[0] != "haac_id":
            reordered = {"haac_id": entry["haac_id"]}
            for k, v in entry.items():
                if k != "haac_id":
                    reordered[k] = v
            entries[i] = reordered
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_haac_id_backfill.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Verify existing tests still pass**

Run: `uv run pytest tests/ -v`
Expected: All existing tests still pass (no regression).

- [ ] **Step 6: Commit**

```bash
git add src/haac/providers/__init__.py tests/test_haac_id_backfill.py
git commit -m "feat: add _ensure_haac_id helper for UUID backfill"
```

---

### Task 3: `git_head_entry` helper

**Files:**
- Modify: `src/haac/providers/__init__.py`
- Modify: `tests/test_haac_id_backfill.py` (add tests)

- [ ] **Step 1: Add failing tests**

Append to `tests/test_haac_id_backfill.py`:

```python
import subprocess
from pathlib import Path

import pytest

from haac.git_ctx import GitContext
from haac.providers import git_head_entry


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit_yaml(repo: Path, rel: str, content: str) -> None:
    (repo / rel).parent.mkdir(parents=True, exist_ok=True)
    (repo / rel).write_text(content)
    subprocess.run(["git", "add", rel], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=repo, check=True)


def test_git_head_entry_finds_by_haac_id(git_repo):
    _commit_yaml(git_repo, "state/entities.yaml", """---
entities:
  - haac_id: abc
    entity_id: switch.old
    friendly_name: Old
""")
    ctx = GitContext(git_repo)
    entry = git_head_entry(ctx, Path("state/entities.yaml"), "entities", "abc")
    assert entry is not None
    assert entry["entity_id"] == "switch.old"


def test_git_head_entry_returns_none_when_missing(git_repo):
    _commit_yaml(git_repo, "state/entities.yaml", """---
entities: []
""")
    ctx = GitContext(git_repo)
    assert git_head_entry(ctx, Path("state/entities.yaml"), "entities", "abc") is None


def test_git_head_entry_returns_none_when_no_head(tmp_path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    ctx = GitContext(tmp_path)
    assert git_head_entry(ctx, Path("state/entities.yaml"), "entities", "abc") is None
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_haac_id_backfill.py -v -k git_head_entry`
Expected: FAIL — `ImportError: cannot import name 'git_head_entry'`

- [ ] **Step 3: Implement `git_head_entry`**

In `src/haac/providers/__init__.py`, add:

```python
from haac.git_ctx import GitContext


def git_head_entry(
    git_ctx: GitContext,
    state_file: Path,
    root_key: str,
    haac_id: str,
) -> dict | None:
    """Look up entry by haac_id in HEAD's version of `state_file`.

    Returns None if the file isn't in HEAD, parses fail, or no match.
    """
    blob = git_ctx.head_blob(state_file)
    if blob is None:
        return None
    try:
        data = yaml.safe_load(blob)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict):
        return None
    entries = data.get(root_key)
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("haac_id") == haac_id:
            return entry
    return None
```

- [ ] **Step 4: Run tests to verify pass**

Run: `uv run pytest tests/test_haac_id_backfill.py -v`
Expected: All pass (7 tests total in this file now).

- [ ] **Step 5: Commit**

```bash
git add src/haac/providers/__init__.py tests/test_haac_id_backfill.py
git commit -m "feat: add git_head_entry for looking up entries by haac_id in HEAD"
```

---

### Task 4: Base `pull` backfills `haac_id`

**Files:**
- Modify: `src/haac/providers/__init__.py:107-136` (the base `pull` method)
- Modify: `tests/test_haac_id_backfill.py` (add integration test)

- [ ] **Step 1: Add failing test**

Append to `tests/test_haac_id_backfill.py`:

```python
from haac.providers.floors import FloorsProvider


class FakeClient:
    def __init__(self, response):
        self._response = response

    async def ws_command(self, *args, **kwargs):
        return self._response


@pytest.mark.asyncio
async def test_base_pull_backfills_haac_id(tmp_path):
    """Base Provider.pull assigns haac_id to newly pulled entries."""
    provider = FloorsProvider()
    client = FakeClient([
        {"floor_id": "f1", "name": "Ground", "icon": ""},
    ])
    await provider.pull(tmp_path, client)

    import yaml
    data = yaml.safe_load((tmp_path / "floors.yaml").read_text())
    assert len(data["floors"]) == 1
    assert UUID_RE.match(data["floors"][0]["haac_id"])


@pytest.mark.asyncio
async def test_base_pull_preserves_existing_haac_id(tmp_path):
    """Second pull of same entry preserves its haac_id."""
    # Seed a floors.yaml with an entry that has a haac_id
    existing_id = str(uuid.uuid4())
    (tmp_path / "floors.yaml").write_text(f"""---
floors:
  - haac_id: {existing_id}
    name: Ground
    icon: ''
""")
    provider = FloorsProvider()
    client = FakeClient([
        {"floor_id": "f1", "name": "Ground", "icon": ""},
    ])
    await provider.pull(tmp_path, client)

    import yaml
    data = yaml.safe_load((tmp_path / "floors.yaml").read_text())
    ground = next(f for f in data["floors"] if f["name"] == "Ground")
    assert ground["haac_id"] == existing_id
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_haac_id_backfill.py -v -k pull`
Expected: FAIL — pulled entries have no `haac_id` field.

- [ ] **Step 3: Update base `pull` to backfill**

In `src/haac/providers/__init__.py`, modify the `pull` method. Replace the current implementation with:

```python
async def pull(self, state_dir: Path, client: HAClient) -> list[str]:
    """Pull current HA state into state file.

    Returns list of names/IDs of newly added items.
    """
    current = await self.read_current(client)
    if self.has_state_file(state_dir):
        desired = await self.read_desired(state_dir)
    else:
        desired = []

    # Default: additive merge by name
    desired_names = set()
    for d in desired:
        name = d.get("name", d.get("entity_id", d.get("match", "")))
        if name:
            desired_names.add(name.lower())

    new_items = []
    new_names = []
    for item in current:
        name = item.get("name", item.get("name_by_user") or item.get("name", ""))
        if name and name.lower() not in desired_names:
            new_items.append(item)
            new_names.append(name)

    merged = desired + new_items
    _ensure_haac_id(merged)  # Backfill any entry missing a haac_id
    if new_items or any("haac_id" not in d for d in desired):
        await self.write_desired(state_dir, merged)

    return new_names
```

- [ ] **Step 4: Verify tests pass**

Run: `uv run pytest tests/test_haac_id_backfill.py tests/test_floors.py -v`
Expected: All pass.

- [ ] **Step 5: Run full suite to check no regression**

Run: `uv run pytest tests/ -v`
Expected: All pre-existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/haac/providers/__init__.py tests/test_haac_id_backfill.py
git commit -m "feat: backfill haac_id in base Provider.pull"
```

---

### Task 5: Allow `haac_id` in `parse_state_file`

**Files:**
- Modify: `src/haac/providers/__init__.py` (in `parse_state_file`)

The `parse_state_file` already permits extra fields — it only validates required ones. But confirm with a test.

- [ ] **Step 1: Add test for haac_id pass-through**

Append to `tests/test_haac_id_backfill.py`:

```python
def test_parse_state_file_passes_through_haac_id(tmp_path):
    from haac.providers import parse_state_file
    p = tmp_path / "floors.yaml"
    p.write_text("""---
floors:
  - haac_id: abc
    name: Ground
""")
    entries = parse_state_file(p, "floors", ["name"])
    assert entries[0]["haac_id"] == "abc"
    assert entries[0]["name"] == "Ground"
```

- [ ] **Step 2: Run to verify pass (no code change needed)**

Run: `uv run pytest tests/test_haac_id_backfill.py::test_parse_state_file_passes_through_haac_id -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_haac_id_backfill.py
git commit -m "test: document haac_id is preserved through parse_state_file"
```

---

### Task 6: Update `entities` provider's custom `pull` to backfill

**Files:**
- Modify: `src/haac/providers/entities.py:105-133`

The entities provider has its own `pull` override. It must also backfill.

- [ ] **Step 1: Add failing test**

Append to `tests/test_haac_id_backfill.py`:

```python
from haac.providers.entities import EntitiesProvider


@pytest.mark.asyncio
async def test_entities_pull_backfills_haac_id(tmp_path):
    provider = EntitiesProvider()
    client = FakeClient([
        {"entity_id": "light.foo", "name": "Foo Light", "icon": ""},
    ])
    await provider.pull(tmp_path, client)

    import yaml
    data = yaml.safe_load((tmp_path / "entities.yaml").read_text())
    assert UUID_RE.match(data["entities"][0]["haac_id"])
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_haac_id_backfill.py::test_entities_pull_backfills_haac_id -v`
Expected: FAIL — no `haac_id` in output.

- [ ] **Step 3: Update `EntitiesProvider.pull` and `write_desired`**

In `src/haac/providers/entities.py`, update `pull` (lines 105-133) to backfill and update `write_desired` to preserve:

```python
async def write_desired(self, state_dir: Path, resources: list[dict]) -> None:
    """Write entities in haac format (haac_id, entity_id, friendly_name, icon)."""
    class _IndentedDumper(yaml.Dumper):
        def increase_indent(self, flow=False, indentless=False):
            return super().increase_indent(flow, False)

    converted = []
    for e in resources:
        name = e.get("friendly_name") or e.get("name") or ""
        icon = e.get("icon") or ""
        haac_id = e.get("haac_id")
        if not name and not icon and not haac_id:
            continue
        entry: dict = {}
        if haac_id:
            entry["haac_id"] = haac_id
        entry["entity_id"] = e.get("entity_id", e.get("id", ""))
        if name:
            entry["friendly_name"] = name
        if icon:
            entry["icon"] = icon
        converted.append(entry)

    if not converted:
        return

    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / self.state_file
    data = {"entities": converted}
    content = yaml.dump(data, Dumper=_IndentedDumper, default_flow_style=False,
                       sort_keys=False, allow_unicode=True)
    path.write_text(f"---\n{content}")

async def pull(self, state_dir: Path, client: HAClient) -> list[str]:
    """Pull entity customizations from HA."""
    from haac.providers import _ensure_haac_id

    current = await self.read_current(client)
    if self.has_state_file(state_dir):
        desired = await self.read_desired(state_dir)
    else:
        desired = []

    desired_ids = {e["entity_id"] for e in desired}

    new_items = []
    new_names = []
    for entity in current:
        eid = entity.get("entity_id", "")
        name = entity.get("name") or ""
        icon = entity.get("icon") or ""
        if eid not in desired_ids and (name or icon):
            entry: dict = {"entity_id": eid}
            if name:
                entry["friendly_name"] = name
            if icon:
                entry["icon"] = icon
            new_items.append(entry)
            new_names.append(eid)

    merged = desired + new_items
    _ensure_haac_id(merged)
    if new_items or any("haac_id" not in d for d in desired):
        await self.write_desired(state_dir, merged)

    return new_names
```

- [ ] **Step 4: Run the test to verify pass**

Run: `uv run pytest tests/test_haac_id_backfill.py tests/test_entities.py -v`
Expected: All pass.

- [ ] **Step 5: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/haac/providers/entities.py tests/test_haac_id_backfill.py
git commit -m "feat: backfill haac_id in EntitiesProvider.pull"
```

---

## Phase B — Rename detection + per-provider apply

### Task 7: Add `"rename"` action to `Change`

**Files:**
- Modify: `src/haac/models.py:20-26`
- Modify: `src/haac/output.py:22-27`
- Create: tests in `tests/test_rename_detection.py`

- [ ] **Step 1: Write failing output test**

Create `tests/test_rename_detection.py`:

```python
"""Tests for rename detection across providers."""
import subprocess
from pathlib import Path

import pytest

from haac.git_ctx import GitContext
from haac.models import Change, PlanResult, ProviderResult
from haac.output import print_plan


def test_print_plan_renders_rename(capsys):
    plan = PlanResult()
    r = ProviderResult(provider_name="entities")
    r.changes.append(Change(
        action="rename",
        resource_type="entity",
        name="switch.smart_plug_mini → switch.smart_plug_tv",
        details=[],
        data={"new_entity_id": "switch.smart_plug_tv"},
        ha_id="switch.smart_plug_mini",
    ))
    plan.results.append(r)
    print_plan(plan)
    out = capsys.readouterr().out
    assert "rename" in out.lower()
    assert "switch.smart_plug_mini" in out
    assert "switch.smart_plug_tv" in out
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_rename_detection.py::test_print_plan_renders_rename -v`
Expected: FAIL — print_plan doesn't handle "rename" action.

- [ ] **Step 3: Update `models.py` docstring**

In `src/haac/models.py:20`, update the `Change` docstring:

```python
@dataclass
class Change:
    action: str  # "create" | "update" | "rename"
    resource_type: str
    name: str
    details: list[str] = field(default_factory=list)
    data: dict = field(default_factory=dict)
    ha_id: str | None = None
```

- [ ] **Step 4: Update `print_plan` and `print_apply_change`**

In `src/haac/output.py`, update the change-rendering logic:

```python
def print_plan(plan: PlanResult) -> None:
    print_warnings(plan.warnings)

    if not plan.has_changes and plan.total_unmanaged == 0:
        console.print("[green]No changes needed — HA matches desired state.[/green]")
        return

    for result in plan.results:
        if not result.changes and not result.unmanaged:
            continue
        if result.changes:
            console.print(f"\n[bold]{result.provider_name.title()}:[/bold]")
            for c in result.changes:
                if c.action == "create":
                    console.print(f"  [green]+[/green] create \"[green]{c.name}[/green]\"")
                elif c.action == "update":
                    detail = f" [dim]({', '.join(c.details)})[/dim]" if c.details else ""
                    console.print(f"  [yellow]~[/yellow] update \"[yellow]{c.name}[/yellow]\"{detail}")
                elif c.action == "rename":
                    detail = f" [dim]({', '.join(c.details)})[/dim]" if c.details else ""
                    console.print(f"  [magenta]→[/magenta] rename \"[magenta]{c.name}[/magenta]\"{detail}")

    all_unmanaged = [u for r in plan.results for u in r.unmanaged]
    if all_unmanaged:
        console.print(f"\n[bold]Unmanaged[/bold] [dim](exists in HA but not in state files):[/dim]")
        console.print("  [dim]Delete with: haac delete <kind:id>[/dim]")
        for u in all_unmanaged:
            console.print(f"  [red]-[/red] \"{u.name}\" [dim]({u.resource_type}:{u.ha_id})[/dim]")

    parts = []
    if plan.total_creates: parts.append(f"{plan.total_creates} to create")
    if plan.total_updates: parts.append(f"{plan.total_updates} to update")
    if plan.total_renames: parts.append(f"{plan.total_renames} to rename")
    if plan.total_unmanaged: parts.append(f"{plan.total_unmanaged} unmanaged")
    console.print(f"\n[bold]Summary:[/bold] {', '.join(parts)}")


def print_apply_change(c: Change) -> None:
    if c.action == "create":
        console.print(f"  [green]+[/green] created {c.resource_type} \"[green]{c.name}[/green]\"")
    elif c.action == "update":
        console.print(f"  [yellow]~[/yellow] updated {c.resource_type} \"[yellow]{c.name}[/yellow]\"")
    elif c.action == "rename":
        console.print(f"  [magenta]→[/magenta] renamed {c.resource_type} \"[magenta]{c.name}[/magenta]\"")
```

- [ ] **Step 5: Add `total_renames` to `PlanResult`**

In `src/haac/models.py`, add the property:

```python
@property
def total_renames(self) -> int:
    return sum(1 for r in self.results for c in r.changes if c.action == "rename")
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_rename_detection.py tests/test_plan_validation.py -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/haac/models.py src/haac/output.py tests/test_rename_detection.py
git commit -m "feat: add rename action to Change model and output"
```

---

### Task 8: Rename detection in `FloorsProvider`

**Files:**
- Modify: `src/haac/providers/floors.py`
- Modify: `tests/test_rename_detection.py`

The pattern: `diff` accepts an optional `git_ctx` via context, and uses `git_head_entry` to detect renames.

- [ ] **Step 1: Add failing test**

Append to `tests/test_rename_detection.py`:

```python
@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def _commit_file(repo: Path, rel: str, content: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    subprocess.run(["git", "-C", str(repo), "add", rel], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True)


def test_floors_rename_detected(git_repo):
    from haac.providers.floors import FloorsProvider

    state = git_repo / "state"
    state.mkdir()
    yaml_content = """---
floors:
  - haac_id: f-abc
    name: Ground
    icon: ''
"""
    _commit_file(git_repo, "state/floors.yaml", yaml_content)

    # User edits name to "Ground Floor"
    (state / "floors.yaml").write_text("""---
floors:
  - haac_id: f-abc
    name: Ground Floor
    icon: ''
""")

    provider = FloorsProvider()
    desired = [{"haac_id": "f-abc", "name": "Ground Floor", "icon": ""}]
    current = [{"floor_id": "ha-123", "name": "Ground", "icon": ""}]
    ctx = {"git_ctx": GitContext(git_repo), "state_dir": state}
    result = provider.diff(desired, current, ctx)

    assert len(result.changes) == 1
    c = result.changes[0]
    assert c.action == "rename"
    assert "Ground" in c.name
    assert "Ground Floor" in c.name
    assert c.ha_id == "ha-123"
    assert c.data.get("name") == "Ground Floor"
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_rename_detection.py::test_floors_rename_detected -v`
Expected: FAIL — no rename detection.

- [ ] **Step 3: Implement rename detection in `FloorsProvider.diff`**

In `src/haac/providers/floors.py`, replace the `diff` method:

```python
def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
    from haac.providers import git_head_entry

    result = ProviderResult(provider_name=self.name)
    context = context or {}
    current_by_name = {f["name"].lower(): f for f in current}
    matched_ha_ids = set()

    git_ctx = context.get("git_ctx")
    state_dir = context.get("state_dir")

    for floor in desired:
        desired_name = floor["name"]
        ha = current_by_name.get(desired_name.lower())

        if ha is not None:
            # Match by name — normal update path
            matched_ha_ids.add(ha["floor_id"])
            details = []
            if ha.get("icon", "") != floor.get("icon", ""):
                details.append(f"icon: {ha.get('icon', '') or '(none)'} → {floor.get('icon', '')}")
            if details:
                result.changes.append(Change(
                    action="update", resource_type="floor", name=desired_name,
                    details=details,
                    data={"name": desired_name, "icon": floor.get("icon", "")},
                    ha_id=ha["floor_id"],
                ))
            continue

        # Name not found in HA — check for rename via git
        rename_change = _try_detect_rename(
            floor=floor, current=current, current_by_name=current_by_name,
            git_ctx=git_ctx, state_dir=state_dir,
            state_file=self.state_file, root_key="floors",
            resource_type="floor",
        )
        if rename_change is not None:
            matched_ha_ids.add(rename_change.ha_id)
            result.changes.append(rename_change)
            continue

        # Truly new floor
        result.changes.append(Change(
            action="create", resource_type="floor", name=desired_name,
            data={"name": desired_name, "icon": floor.get("icon", "")},
        ))

    for f in current:
        if f["floor_id"] not in matched_ha_ids:
            result.unmanaged.append(Unmanaged(
                resource_type="floor", ha_id=f["floor_id"], name=f["name"],
            ))

    return result
```

- [ ] **Step 4: Implement `_try_detect_rename` helper in providers/__init__.py**

In `src/haac/providers/__init__.py`, add:

```python
def _try_detect_rename(
    *,
    floor: dict | None = None,      # alias for "the desired entry"
    desired_entry: dict | None = None,
    current: list[dict],
    current_by_name: dict | None = None,
    current_by_id: dict | None = None,
    git_ctx: GitContext | None,
    state_dir: Path | None,
    state_file: str,
    root_key: str,
    resource_type: str,
    ha_id_field: str = "floor_id",      # caller overrides per provider
    name_field: str = "name",
) -> "Change | None":
    """Detect a rename: desired has new HA name/ID, HEAD had old one.

    Returns a Change(action="rename") or None if not detected.
    """
    from haac.models import Change

    entry = desired_entry if desired_entry is not None else floor
    if entry is None:
        return None
    haac_id = entry.get("haac_id")
    if not haac_id or git_ctx is None or state_dir is None:
        return None

    old_entry = git_head_entry(
        git_ctx, Path(state_dir) / state_file, root_key, haac_id,
    )
    if old_entry is None:
        return None

    old_name = old_entry.get(name_field)
    if not old_name:
        return None

    # Find the HA resource by old name
    old_ha = None
    if current_by_name is not None:
        old_ha = current_by_name.get(old_name.lower())
    if old_ha is None:
        return None

    new_name = entry.get(name_field)
    details = [f"{name_field}: {old_name} → {new_name}"]
    return Change(
        action="rename",
        resource_type=resource_type,
        name=f"{old_name} → {new_name}",
        details=details,
        data={name_field: new_name},
        ha_id=old_ha[ha_id_field],
    )
```

- [ ] **Step 5: Update `floors.py` imports**

At top of `src/haac/providers/floors.py`:

```python
from haac.providers import Provider, parse_state_file, register, _try_detect_rename
```

- [ ] **Step 6: Implement rename in `apply_change`**

In `src/haac/providers/floors.py`, update `apply_change`:

```python
async def apply_change(self, client: HAClient, change: Change) -> None:
    if change.action == "create":
        await client.ws_command("config/floor_registry/create", **change.data)
    elif change.action == "update":
        await client.ws_command("config/floor_registry/update", floor_id=change.ha_id, **change.data)
    elif change.action == "rename":
        # For floors, rename = updating the name (floor_id is immutable in HA)
        await client.ws_command("config/floor_registry/update", floor_id=change.ha_id, **change.data)
```

- [ ] **Step 7: Run tests**

Run: `uv run pytest tests/test_rename_detection.py::test_floors_rename_detected tests/test_floors.py -v`
Expected: All pass.

- [ ] **Step 8: Commit**

```bash
git add src/haac/providers/__init__.py src/haac/providers/floors.py tests/test_rename_detection.py
git commit -m "feat: floors rename detection and apply"
```

---

### Task 9: Rename detection in `LabelsProvider`, `AreasProvider`, `HelpersProvider`

Apply the same pattern to labels, areas, helpers. These providers all use name-based matching.

**Files:**
- Modify: `src/haac/providers/labels.py`
- Modify: `src/haac/providers/areas.py`
- Modify: `src/haac/providers/helpers.py`
- Modify: `tests/test_rename_detection.py`

- [ ] **Step 1: Add failing tests for labels/areas/helpers**

Append to `tests/test_rename_detection.py`:

```python
def test_labels_rename_detected(git_repo):
    from haac.providers.labels import LabelsProvider

    state = git_repo / "state"
    state.mkdir()
    _commit_file(git_repo, "state/labels.yaml", """---
labels:
  - haac_id: l-abc
    name: Nightly
    color: blue
""")
    (state / "labels.yaml").write_text("""---
labels:
  - haac_id: l-abc
    name: After Dark
    color: blue
""")
    provider = LabelsProvider()
    desired = [{"haac_id": "l-abc", "name": "After Dark", "color": "blue"}]
    current = [{"label_id": "l-ha-1", "name": "Nightly", "color": "blue"}]
    result = provider.diff(desired, current, {"git_ctx": GitContext(git_repo), "state_dir": state})
    assert any(c.action == "rename" for c in result.changes)


def test_areas_rename_detected(git_repo):
    from haac.providers.areas import AreasProvider

    state = git_repo / "state"
    state.mkdir()
    _commit_file(git_repo, "state/areas.yaml", """---
areas:
  - haac_id: a-abc
    id: living_room
    name: Living Room
    floor: ground
""")
    (state / "areas.yaml").write_text("""---
areas:
  - haac_id: a-abc
    id: living_room
    name: Lounge
    floor: ground
""")
    provider = AreasProvider()
    desired = [{"haac_id": "a-abc", "id": "living_room", "name": "Lounge", "floor": "ground"}]
    current = [{"area_id": "living_room", "name": "Living Room", "floor_id": "ground"}]
    result = provider.diff(desired, current, {
        "git_ctx": GitContext(git_repo), "state_dir": state,
        "floors": [{"floor_id": "ground", "name": "Ground"}],
        "desired_floors": [{"haac_id": "f-x", "id": "ground", "name": "Ground"}],
    })
    assert any(c.action == "rename" for c in result.changes)


def test_helpers_rename_detected(git_repo):
    from haac.providers.helpers import HelpersProvider

    state = git_repo / "state"
    state.mkdir()
    _commit_file(git_repo, "state/helpers.yaml", """---
input_booleans:
  - haac_id: h-abc
    id: guest_mode
    name: Guest Mode
""")
    (state / "helpers.yaml").write_text("""---
input_booleans:
  - haac_id: h-abc
    id: guest_mode
    name: Visitor Mode
""")
    provider = HelpersProvider()
    desired = [{"haac_id": "h-abc", "id": "guest_mode", "name": "Visitor Mode"}]
    current = [{"id": "guest_mode", "name": "Guest Mode"}]
    result = provider.diff(desired, current, {"git_ctx": GitContext(git_repo), "state_dir": state})
    assert any(c.action == "rename" for c in result.changes)
```

- [ ] **Step 2: Run tests — expect failures**

Run: `uv run pytest tests/test_rename_detection.py -v -k "rename_detected"`
Expected: 3 new failures (labels, areas, helpers — floors already passing).

- [ ] **Step 3: Update `LabelsProvider.diff` and `apply_change`**

In `src/haac/providers/labels.py`, mirror the floors pattern:

```python
from haac.providers import Provider, parse_state_file, register, _try_detect_rename

# ... in the class:

def diff(self, desired, current, context=None):
    result = ProviderResult(provider_name=self.name)
    context = context or {}
    current_by_name = {l["name"].lower(): l for l in current}
    matched_ha_ids = set()

    for label in desired:
        desired_name = label["name"]
        ha = current_by_name.get(desired_name.lower())
        if ha is not None:
            matched_ha_ids.add(ha["label_id"])
            details = []
            if ha.get("color", "") != label.get("color", ""):
                details.append(f"color: {ha.get('color', '') or '(none)'} → {label.get('color', '')}")
            if ha.get("icon", "") != label.get("icon", ""):
                details.append(f"icon: {ha.get('icon', '') or '(none)'} → {label.get('icon', '')}")
            if details:
                result.changes.append(Change(
                    action="update", resource_type="label", name=desired_name,
                    details=details,
                    data={"name": desired_name, "color": label.get("color", ""), "icon": label.get("icon", "")},
                    ha_id=ha["label_id"],
                ))
            continue

        rename_change = _try_detect_rename(
            desired_entry=label, current=current, current_by_name=current_by_name,
            git_ctx=context.get("git_ctx"), state_dir=context.get("state_dir"),
            state_file=self.state_file, root_key="labels",
            resource_type="label", ha_id_field="label_id", name_field="name",
        )
        if rename_change is not None:
            # Merge in color/icon from the desired entry
            rename_change.data["color"] = label.get("color", "")
            rename_change.data["icon"] = label.get("icon", "")
            matched_ha_ids.add(rename_change.ha_id)
            result.changes.append(rename_change)
            continue

        result.changes.append(Change(
            action="create", resource_type="label", name=desired_name,
            data={"name": desired_name, "color": label.get("color", ""), "icon": label.get("icon", "")},
        ))

    for l in current:
        if l["label_id"] not in matched_ha_ids:
            result.unmanaged.append(Unmanaged(resource_type="label", ha_id=l["label_id"], name=l["name"]))

    return result

async def apply_change(self, client, change):
    if change.action == "create":
        await client.ws_command("config/label_registry/create", **change.data)
    elif change.action in ("update", "rename"):
        await client.ws_command("config/label_registry/update", label_id=change.ha_id, **change.data)
```

Note: if existing `LabelsProvider` has different field handling, preserve that — the diff above shows the structural change only. Read the current `diff` before editing to preserve any label-specific fields.

- [ ] **Step 4: Update `AreasProvider` with the same pattern**

In `src/haac/providers/areas.py`, apply the same transformation. Areas key on `area_id` in HA and on `id` in desired YAML. Pass `name_field="name"` to `_try_detect_rename`. The rename call is `config/area_registry/update` with `area_id`. Existing floor-resolution logic stays.

Add to `apply_change`:
```python
elif change.action == "rename":
    await client.ws_command("config/area_registry/update", area_id=change.ha_id, **change.data)
```

- [ ] **Step 5: Update `HelpersProvider`**

In `src/haac/providers/helpers.py`, apply the same pattern with:
- `ha_id_field="id"` (HA's `id` field on input_boolean list items)
- `name_field="name"`
- Rename calls `input_boolean/update` with `input_boolean_id=change.ha_id`

Add to `apply_change`:
```python
elif change.action == "rename":
    await client.ws_command(
        "input_boolean/update",
        input_boolean_id=change.ha_id,
        name=change.data.get("name", ""),
        icon=change.data.get("icon", ""),
    )
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_rename_detection.py tests/test_labels.py tests/test_areas.py tests/test_helpers.py -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/haac/providers/labels.py src/haac/providers/areas.py src/haac/providers/helpers.py tests/test_rename_detection.py
git commit -m "feat: rename detection for labels, areas, helpers"
```

---

### Task 10: Rename detection in `EntitiesProvider`

Entities are keyed by `entity_id` (stable HA ID). Renaming = sending `new_entity_id` on `config/entity_registry/update`.

**Files:**
- Modify: `src/haac/providers/entities.py`
- Modify: `tests/test_rename_detection.py`

- [ ] **Step 1: Add failing test**

Append to `tests/test_rename_detection.py`:

```python
def test_entities_rename_detected(git_repo):
    from haac.providers.entities import EntitiesProvider

    state = git_repo / "state"
    state.mkdir()
    _commit_file(git_repo, "state/entities.yaml", """---
entities:
  - haac_id: e-abc
    entity_id: switch.smart_plug_mini
    friendly_name: Mini Plug
""")
    (state / "entities.yaml").write_text("""---
entities:
  - haac_id: e-abc
    entity_id: switch.smart_plug_tv
    friendly_name: Mini Plug
""")
    provider = EntitiesProvider()
    desired = [{"haac_id": "e-abc", "entity_id": "switch.smart_plug_tv", "friendly_name": "Mini Plug"}]
    current = [{"entity_id": "switch.smart_plug_mini", "name": "Mini Plug", "icon": ""}]
    result = provider.diff(desired, current, {"git_ctx": GitContext(git_repo), "state_dir": state})
    rename = next((c for c in result.changes if c.action == "rename"), None)
    assert rename is not None
    assert rename.data.get("new_entity_id") == "switch.smart_plug_tv"
    assert rename.ha_id == "switch.smart_plug_mini"
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_rename_detection.py::test_entities_rename_detected -v`
Expected: FAIL.

- [ ] **Step 3: Update `EntitiesProvider.diff`**

In `src/haac/providers/entities.py`, replace `diff`:

```python
def diff(self, desired: list[dict], current: list[dict], context: dict | None = None) -> ProviderResult:
    from haac.providers import git_head_entry

    result = ProviderResult(provider_name=self.name)
    context = context or {}
    current_by_id = {e["entity_id"]: e for e in current}

    git_ctx = context.get("git_ctx")
    state_dir = context.get("state_dir")

    for entity in desired:
        eid = entity["entity_id"]
        ha_entity = current_by_id.get(eid)

        if ha_entity is None:
            # Potential rename: look up haac_id in HEAD
            haac_id = entity.get("haac_id")
            if haac_id and git_ctx is not None and state_dir is not None:
                old_entry = git_head_entry(
                    git_ctx, Path(state_dir) / self.state_file, "entities", haac_id,
                )
                if old_entry is not None:
                    old_eid = old_entry.get("entity_id")
                    old_ha = current_by_id.get(old_eid) if old_eid else None
                    if old_ha is not None:
                        details = [f"entity_id: {old_eid} → {eid}"]
                        data: dict = {"new_entity_id": eid}
                        desired_name = entity.get("friendly_name", "")
                        current_name = old_ha.get("name") or ""
                        if desired_name and desired_name != current_name:
                            details.append(f"name: {current_name or '(default)'} → {desired_name}")
                            data["name"] = desired_name
                        desired_icon = entity.get("icon", "")
                        current_icon = old_ha.get("icon") or ""
                        if desired_icon and desired_icon != current_icon:
                            details.append(f"icon: {current_icon or '(default)'} → {desired_icon}")
                            data["icon"] = desired_icon
                        result.changes.append(Change(
                            action="rename",
                            resource_type="entity",
                            name=f"{old_eid} → {eid}",
                            details=details,
                            data=data,
                            ha_id=old_eid,
                        ))
                        continue
            # Not found in HA, no rename detected — skip (can't create entities)
            continue

        # Entity found by ID — update fields
        details = []
        desired_name = entity.get("friendly_name", "")
        current_name = ha_entity.get("name") or ""
        if desired_name and desired_name != current_name:
            details.append(f"name: {current_name or '(default)'} → {desired_name}")

        desired_icon = entity.get("icon", "")
        current_icon = ha_entity.get("icon") or ""
        if desired_icon and desired_icon != current_icon:
            details.append(f"icon: {current_icon or '(default)'} → {desired_icon}")

        if details:
            data = {"entity_id": eid}
            if desired_name:
                data["name"] = desired_name
            if desired_icon:
                data["icon"] = desired_icon
            result.changes.append(Change(
                action="update", resource_type="entity",
                name=eid, details=details, data=data,
                ha_id=eid,
            ))

    return result
```

- [ ] **Step 4: Update `apply_change`**

Replace `apply_change` in `src/haac/providers/entities.py`:

```python
async def apply_change(self, client: HAClient, change: Change) -> None:
    if change.action == "rename":
        # data contains new_entity_id plus optional name/icon
        await client.ws_command(
            "config/entity_registry/update",
            entity_id=change.ha_id,
            **change.data,
        )
    else:
        data = {k: v for k, v in change.data.items() if k != "entity_id"}
        await client.ws_command(
            "config/entity_registry/update",
            entity_id=change.data["entity_id"],
            **data,
        )
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_rename_detection.py tests/test_entities.py -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/haac/providers/entities.py tests/test_rename_detection.py
git commit -m "feat: entity rename via new_entity_id"
```

---

### Task 11: Rename detection in `AutomationsProvider` and `ScenesProvider` (two-step)

These use REST, and HA has no atomic rename. Strategy: POST new config, then DELETE old.

**Files:**
- Modify: `src/haac/providers/automations.py`
- Modify: `src/haac/providers/scenes.py`
- Modify: `tests/test_rename_detection.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_rename_detection.py`:

```python
def test_automations_rename_detected(git_repo):
    from haac.providers.automations import AutomationsProvider

    state = git_repo / "state"
    state.mkdir()
    _commit_file(git_repo, "state/automations.yaml", """---
automations:
  - haac_id: au-abc
    id: '1001'
    alias: Morning
    trigger: []
    action: []
""")
    (state / "automations.yaml").write_text("""---
automations:
  - haac_id: au-abc
    id: '2002'
    alias: Morning
    trigger: []
    action: []
""")
    provider = AutomationsProvider()
    desired = [{"haac_id": "au-abc", "id": "2002", "alias": "Morning", "trigger": [], "action": []}]
    current = [{"id": "1001", "alias": "Morning", "trigger": [], "action": []}]
    result = provider.diff(desired, current, {"git_ctx": GitContext(git_repo), "state_dir": state})
    rename = next((c for c in result.changes if c.action == "rename"), None)
    assert rename is not None
    assert rename.ha_id == "1001"
    assert rename.data["new_id"] == "2002"


def test_scenes_rename_detected(git_repo):
    from haac.providers.scenes import ScenesProvider

    state = git_repo / "state"
    state.mkdir()
    _commit_file(git_repo, "state/scenes.yaml", """---
scenes:
  - haac_id: sc-abc
    id: '5001'
    name: Evening
    entities: {}
""")
    (state / "scenes.yaml").write_text("""---
scenes:
  - haac_id: sc-abc
    id: '6002'
    name: Evening
    entities: {}
""")
    provider = ScenesProvider()
    desired = [{"haac_id": "sc-abc", "id": "6002", "name": "Evening", "entities": {}}]
    current = [{"id": "5001", "name": "Evening", "entities": {}}]
    result = provider.diff(desired, current, {"git_ctx": GitContext(git_repo), "state_dir": state})
    rename = next((c for c in result.changes if c.action == "rename"), None)
    assert rename is not None
    assert rename.data["new_id"] == "6002"
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_rename_detection.py -k "automations_rename or scenes_rename" -v`
Expected: FAIL.

- [ ] **Step 3: Update `AutomationsProvider.diff`**

In `src/haac/providers/automations.py`, modify the `diff` to detect renames. Automations key by `id`. Before the final "create" path, check for rename:

```python
# Inside diff(), where you currently emit action="create" for a desired automation
# whose id isn't in current:

haac_id = automation.get("haac_id")
git_ctx = context.get("git_ctx")
state_dir = context.get("state_dir")
if haac_id and git_ctx is not None and state_dir is not None:
    old_entry = git_head_entry(
        git_ctx, Path(state_dir) / self.state_file, "automations", haac_id,
    )
    if old_entry is not None:
        old_id = old_entry.get("id")
        if old_id and any(a.get("id") == old_id for a in current):
            # Emit rename
            result.changes.append(Change(
                action="rename",
                resource_type="automation",
                name=f"{old_id} → {automation['id']}",
                details=[f"id: {old_id} → {automation['id']}"],
                data={"new_id": automation["id"], "config": automation},
                ha_id=old_id,
            ))
            continue
```

(Preserve the rest of the current `diff` logic — only add this branch before the create.)

Since I haven't read automations.py yet, read it first and integrate the rename branch where appropriate. Keep the test expectation as-is.

- [ ] **Step 4: Update `AutomationsProvider.apply_change` with two-step**

```python
elif change.action == "rename":
    new_id = change.data["new_id"]
    config = change.data["config"]
    # Post new first
    await client.rest_post(f"/api/config/automation/config/{new_id}", json=config)
    # Then delete old
    try:
        await client.rest_delete(f"/api/config/automation/config/{change.ha_id}")
    except Exception as e:
        # Leave duplicate on DELETE failure — surface to user
        from haac.output import console
        console.print(f"[yellow]Warning: renamed automation created new id "
                      f"{new_id} but failed to delete old id {change.ha_id}: {e}[/yellow]")
```

(Adjust method names to match `HAClient`'s REST helpers — read `src/haac/client.py` first.)

- [ ] **Step 5: Mirror changes in `ScenesProvider`**

In `src/haac/providers/scenes.py`, same pattern with `/api/config/scene/config/`.

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_rename_detection.py tests/test_automations.py tests/test_scenes.py -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/haac/providers/automations.py src/haac/providers/scenes.py tests/test_rename_detection.py
git commit -m "feat: automation and scene rename via POST-new DELETE-old"
```

---

### Task 12: Pass `git_ctx` through plan/apply context

**Files:**
- Modify: `src/haac/cli.py`

- [ ] **Step 1: Add failing integration test**

Create `tests/test_cli_rename_integration.py`:

```python
"""End-to-end test: plan picks up rename via GitContext from config."""
import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def ha_repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


def test_plan_builds_context_with_git_ctx(ha_repo, monkeypatch):
    """_build_context puts a GitContext under 'git_ctx' and state_dir under 'state_dir'."""
    from haac.cli import _build_context
    from haac.config import Config
    import asyncio

    state = ha_repo / "state"
    state.mkdir()
    (ha_repo / "haac.yaml").write_text('ha_url: "http://x"\n')

    cfg = Config(ha_url="http://x", ha_token="t", state_dir=state, project_dir=ha_repo)

    class FakeClient:
        async def ws_command(self, *a, **k): return []
        async def rest_get(self, *a, **k): return []

    ctx = asyncio.run(_build_context([], FakeClient(), cfg))
    assert "git_ctx" in ctx
    assert "state_dir" in ctx
    assert ctx["state_dir"] == state
```

- [ ] **Step 2: Confirm failure**

Run: `uv run pytest tests/test_cli_rename_integration.py -v`
Expected: FAIL.

- [ ] **Step 3: Update `_build_context` in cli.py**

In `src/haac/cli.py`, update `_build_context`:

```python
async def _build_context(providers, client, config):
    """Build context dict with desired + current state for all providers."""
    from haac.git_ctx import GitContext

    context = {
        "git_ctx": GitContext(config.project_dir),
        "state_dir": config.state_dir,
    }
    for p in providers:
        if p.has_state_file(config.state_dir):
            context[f"desired_{p.name}"] = await p.read_desired(config.state_dir)
        context[p.name] = await p.read_current(client)
    return context
```

Read `src/haac/config.py` to confirm `Config` has a `project_dir` attribute. If it doesn't, add it — `project_dir` is the directory containing `haac.yaml`.

- [ ] **Step 4: Add `project_dir` to Config if missing**

In `src/haac/config.py`, ensure `Config` carries `project_dir: Path` and `load_config` sets it to the cwd (or the explicit config dir).

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/ -v`
Expected: All pass.

- [ ] **Step 6: Commit**

```bash
git add src/haac/cli.py src/haac/config.py tests/test_cli_rename_integration.py
git commit -m "feat: pass GitContext and state_dir through plan/apply context"
```

---

### Task 13: Rename handling in apply flow

**Files:**
- Modify: `src/haac/cli.py:62-96` (the `_run_apply` function)

The existing apply loop refetches current state after each provider. Renames need the same treatment — no additional code needed IF the rename is emitted as a regular Change. Verify.

- [ ] **Step 1: Add test that apply invokes rename**

Append to `tests/test_cli_rename_integration.py`:

```python
import asyncio
from unittest.mock import AsyncMock

from haac.models import Change


@pytest.mark.asyncio
async def test_apply_invokes_rename_api(tmp_path):
    """apply calls provider.apply_change for rename actions."""
    from haac.providers.entities import EntitiesProvider

    provider = EntitiesProvider()
    client = AsyncMock()
    client.ws_command = AsyncMock()

    change = Change(
        action="rename",
        resource_type="entity",
        name="switch.a → switch.b",
        data={"new_entity_id": "switch.b"},
        ha_id="switch.a",
    )
    await provider.apply_change(client, change)

    client.ws_command.assert_called_once()
    args, kwargs = client.ws_command.call_args
    assert args[0] == "config/entity_registry/update"
    assert kwargs["entity_id"] == "switch.a"
    assert kwargs["new_entity_id"] == "switch.b"
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/test_cli_rename_integration.py -v`
Expected: PASS (apply_change already supports rename from Task 10).

- [ ] **Step 3: Commit**

```bash
git add tests/test_cli_rename_integration.py
git commit -m "test: verify apply dispatches rename via provider.apply_change"
```

---

## Phase C — Interactive reference rewriting

### Task 14: Reference scanning module

**Files:**
- Create: `src/haac/rename_refs.py`
- Create: `tests/test_rename_refs.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_rename_refs.py`:

```python
"""Tests for repo-wide reference scanning and rewriting."""
import subprocess
from pathlib import Path

import pytest

from haac.git_ctx import GitContext
from haac.rename_refs import scan_references, rewrite_references


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / ".gitignore").write_text(".venv/\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", ".gitignore"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)
    return tmp_path


def _write(repo: Path, rel: str, content: str):
    p = repo / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def test_scan_finds_token_matches(repo):
    _write(repo, "scenes.yaml", "entities:\n  switch.smart_plug_mini:\n    state: 'on'\n")
    _write(repo, "automations.yaml", "target:\n  entity_id: switch.smart_plug_mini\n")
    hits = scan_references(GitContext(repo), "switch.smart_plug_mini")
    assert len(hits) == 2
    paths = {h.path.as_posix() for h in hits}
    assert paths == {"scenes.yaml", "automations.yaml"}


def test_scan_respects_word_boundaries(repo):
    _write(repo, "a.yaml", "switch.smart_plug_mini_extra: 1\n")
    hits = scan_references(GitContext(repo), "switch.smart_plug_mini")
    assert hits == []


def test_scan_skips_gitignored(repo):
    (repo / ".venv").mkdir()
    _write(repo, ".venv/x.yaml", "switch.smart_plug_mini\n")
    hits = scan_references(GitContext(repo), "switch.smart_plug_mini")
    assert hits == []


def test_rewrite_replaces_all(repo):
    _write(repo, "scenes.yaml", "switch.smart_plug_mini: on\n")
    _write(repo, "auto.yaml", "entity: switch.smart_plug_mini\n")
    paths = rewrite_references(
        GitContext(repo), "switch.smart_plug_mini", "switch.smart_plug_tv",
    )
    assert (repo / "scenes.yaml").read_text() == "switch.smart_plug_tv: on\n"
    assert (repo / "auto.yaml").read_text() == "entity: switch.smart_plug_tv\n"
    assert len(paths) == 2


def test_rewrite_rolls_back_on_error(repo, monkeypatch):
    _write(repo, "a.yaml", "switch.smart_plug_mini\n")
    (repo / "a.yaml").chmod(0o444)
    try:
        with pytest.raises(PermissionError):
            rewrite_references(
                GitContext(repo), "switch.smart_plug_mini", "switch.smart_plug_tv",
            )
    finally:
        (repo / "a.yaml").chmod(0o644)
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_rename_refs.py -v`
Expected: FAIL — `ModuleNotFoundError: haac.rename_refs`.

- [ ] **Step 3: Implement `rename_refs.py`**

Create `src/haac/rename_refs.py`:

```python
"""Scan and rewrite references across the repo when an HA ID is renamed."""

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
    """Replace whole-token occurrences of `old` with `new` in tracked/untracked files.

    Pre-checks that all candidate files are writable before modifying any.
    On any write failure, restores via git checkout. Returns list of paths changed.
    """
    pattern = _token_regex(old)
    hits = scan_references(git_ctx, old)
    touched = []
    files_to_write: list[tuple[Path, str]] = []

    # Build all replacements in memory first
    seen_paths = set()
    for hit in hits:
        if hit.path in seen_paths:
            continue
        seen_paths.add(hit.path)
        full = git_ctx.root / hit.path
        content = full.read_text()
        updated = pattern.sub(new, content)
        if updated != content:
            files_to_write.append((full, updated))

    # Pre-check writability
    for full, _ in files_to_write:
        if not full.is_file() or not _writable(full):
            raise PermissionError(f"not writable: {full}")

    # Write all
    written: list[Path] = []
    try:
        for full, content in files_to_write:
            full.write_text(content)
            written.append(full.relative_to(git_ctx.root))
            touched.append(full.relative_to(git_ctx.root))
    except Exception:
        # Roll back all writes
        if written:
            git_ctx.checkout(written)
        raise

    return touched


def _writable(path: Path) -> bool:
    import os
    return os.access(path, os.W_OK)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_rename_refs.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add src/haac/rename_refs.py tests/test_rename_refs.py
git commit -m "feat: add rename_refs for repo-wide reference scan and rewrite"
```

---

### Task 15: Interactive rewrite prompt + re-plan loop

**Files:**
- Modify: `src/haac/cli.py`
- Modify: `src/haac/output.py`

- [ ] **Step 1: Add output helper for preview**

In `src/haac/output.py`, add:

```python
def print_ref_preview(old: str, new: str, hits: list) -> None:
    """Print grouped preview of references about to be rewritten."""
    console.print(f"\n[bold]References to {old}:[/bold]")
    last_path = None
    for hit in hits:
        if hit.path != last_path:
            console.print(f"\n  [cyan]{hit.path}[/cyan]")
            last_path = hit.path
        console.print(f"    {hit.line_number}: {hit.line.rstrip()}")
    console.print(f"\n  [dim]{len(hits)} references across "
                  f"{len({h.path for h in hits})} files[/dim]")
```

- [ ] **Step 2: Wire rename-refs into `_run_plan`**

In `src/haac/cli.py`, update `_run_plan`:

```python
async def _run_plan(config, rename_refs_mode="prompt"):
    """rename_refs_mode: 'prompt' (default), 'yes', 'no'."""
    plan = await _plan_once(config)
    print_plan(plan)

    rename_changes = [
        (r.provider_name, c) for r in plan.results for c in r.changes if c.action == "rename"
    ]
    if rename_changes and rename_refs_mode != "no":
        if await _handle_rename_refs(config, rename_changes, rename_refs_mode):
            console.print("\n[bold]Re-planning with updated references...[/bold]")
            plan = await _plan_once(config)
            print_plan(plan)
    return plan


async def _plan_once(config) -> "PlanResult":
    """Run one pass of plan without any interactive side effects."""
    plan = PlanResult()
    async with HAClient(config.ha_url, config.ha_token) as client:
        providers = get_providers()
        context = await _build_context(providers, client, config)
        desired_state = {
            p.name: context[f"desired_{p.name}"]
            for p in providers if f"desired_{p.name}" in context
        }
        plan.warnings = validate_references(desired_state)
        for provider in providers:
            if not provider.has_state_file(config.state_dir):
                continue
            desired = context.get(f"desired_{provider.name}", [])
            current = context.get(provider.name, [])
            result = provider.diff(desired, current, context)
            plan.results.append(result)
    return plan
```

- [ ] **Step 3: Add `_handle_rename_refs`**

In `src/haac/cli.py`, add:

```python
import sys


async def _handle_rename_refs(config, rename_changes, mode: str) -> bool:
    """Prompt user, scan, preview, rewrite. Returns True if any rewrite happened."""
    from haac.git_ctx import GitContext
    from haac.rename_refs import scan_references, rewrite_references
    from haac.output import print_ref_preview

    git_ctx = GitContext(config.project_dir)
    if not git_ctx.is_repo():
        return False

    rewrote_any = False
    for provider_name, change in rename_changes:
        old_id = change.ha_id
        new_id = change.data.get("new_entity_id") or change.data.get("new_id") or change.data.get("name")
        if not old_id or not new_id:
            continue

        # Prompt for scan
        if mode == "prompt":
            if not sys.stdin.isatty():
                continue
            console.print(f"\n[bold]Detected rename:[/bold] {old_id} → {new_id}")
            answer = input("Search for references in the repo? [Y/n] ").strip().lower()
            if answer and answer != "y":
                continue

        hits = scan_references(git_ctx, old_id)
        if not hits:
            console.print(f"  [dim]No references found for {old_id}.[/dim]")
            continue

        print_ref_preview(old_id, new_id, hits)

        if mode == "prompt":
            answer = input(f"\nRewrite {len(hits)} references? [y/N] ").strip().lower()
            if answer != "y":
                continue
        elif mode == "no":
            continue
        # mode == "yes" falls through

        try:
            changed = rewrite_references(git_ctx, old_id, new_id)
            console.print(f"  [green]Rewrote {len(changed)} files.[/green]")
            rewrote_any = True
        except Exception as e:
            console.print(f"  [red]Rewrite failed: {e}[/red]")

    return rewrote_any
```

- [ ] **Step 4: Add CLI flags**

In `src/haac/cli.py` argparse setup:

```python
plan_parser = subparsers.add_parser("plan", help="Show pending changes")
plan_parser.add_argument("--no-rename-refs", action="store_true")
plan_parser.add_argument("--yes-rename-refs", action="store_true")

apply_parser = subparsers.add_parser("apply", help="Apply changes")
apply_parser.add_argument("--no-rename-refs", action="store_true")
apply_parser.add_argument("--yes-rename-refs", action="store_true")
```

And in the dispatch:

```python
def _refs_mode(args) -> str:
    if args.yes_rename_refs:
        return "yes"
    if args.no_rename_refs:
        return "no"
    return "prompt"

# in main:
elif args.command == "plan":
    asyncio.run(_run_plan(config, rename_refs_mode=_refs_mode(args)))
elif args.command == "apply":
    asyncio.run(_run_apply(config, rename_refs_mode=_refs_mode(args)))
```

- [ ] **Step 5: Add integration test**

Create `tests/test_rename_refs_flow.py`:

```python
"""Integration: plan triggers reference rewriting via auto-answered prompts."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.mark.asyncio
async def test_handle_rename_refs_yes_mode_rewrites(repo):
    from haac.cli import _handle_rename_refs
    from haac.config import Config
    from haac.models import Change

    (repo / "scenes.yaml").write_text("switch.old\n")
    subprocess.run(["git", "-C", str(repo), "add", "scenes.yaml"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "x"], check=True)
    (repo / "scenes.yaml").write_text("switch.old: x\n")  # dirty working tree

    config = Config(ha_url="x", ha_token="t", state_dir=repo / "state", project_dir=repo)
    changes = [("entities", Change(
        action="rename", resource_type="entity",
        name="switch.old → switch.new",
        data={"new_entity_id": "switch.new"}, ha_id="switch.old",
    ))]
    result = await _handle_rename_refs(config, changes, "yes")
    assert result is True
    assert "switch.new" in (repo / "scenes.yaml").read_text()
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/test_rename_refs.py tests/test_rename_refs_flow.py -v`
Expected: All pass.

- [ ] **Step 7: Commit**

```bash
git add src/haac/cli.py src/haac/output.py tests/test_rename_refs_flow.py
git commit -m "feat: interactive reference rewriting with re-plan"
```

---

### Task 16: Apply flow runs the same rewrite logic before HA calls

**Files:**
- Modify: `src/haac/cli.py`

- [ ] **Step 1: Update `_run_apply`**

Replace `_run_apply` in `src/haac/cli.py`:

```python
async def _run_apply(config, rename_refs_mode="prompt", commit_mode="prompt"):
    # Run plan + rewrite + re-plan to stabilize the repo before applying
    plan = await _plan_once(config)
    rename_changes = [
        (r.provider_name, c) for r in plan.results for c in r.changes if c.action == "rename"
    ]
    if rename_changes and rename_refs_mode != "no":
        if await _handle_rename_refs(config, rename_changes, rename_refs_mode):
            console.print("\n[bold]Re-planning with updated references...[/bold]")
            plan = await _plan_once(config)

    print_warnings(plan.warnings)

    any_changes = False
    touched_paths: set[Path] = set()
    async with HAClient(config.ha_url, config.ha_token) as client:
        providers = get_providers()
        context = await _build_context(providers, client, config)

        for provider in providers:
            if not provider.has_state_file(config.state_dir):
                continue
            desired = context.get(f"desired_{provider.name}", [])
            current = context.get(provider.name, [])
            result = provider.diff(desired, current, context)

            if result.changes:
                any_changes = True
                console.print(f"\n[bold]{result.provider_name.title()}:[/bold]")
                for change in result.changes:
                    await provider.apply_change(client, change)
                    print_apply_change(change)
                context[provider.name] = await provider.read_current(client)

        if not any_changes and not touched_paths:
            console.print("[green]No changes needed — HA matches desired state.[/green]")
        else:
            console.print("\n[bold green]Done.[/bold green]")
```

- [ ] **Step 2: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All pass.

- [ ] **Step 3: Commit**

```bash
git add src/haac/cli.py
git commit -m "feat: apply handles rename-refs before HA calls"
```

---

## Phase D — Auto-commit after apply

### Task 17: Track haac-touched paths during apply

**Files:**
- Modify: `src/haac/cli.py`
- Modify: `src/haac/rename_refs.py` (return tracked paths)

- [ ] **Step 1: Add failing test**

Create `tests/test_auto_commit.py`:

```python
"""Tests for scoped auto-commit after apply."""
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def repo(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    (tmp_path / "seed.txt").write_text("")
    subprocess.run(["git", "-C", str(tmp_path), "add", "seed.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "init"], check=True)
    return tmp_path


def test_auto_commit_adds_only_touched_paths(repo):
    from haac.cli import _do_auto_commit
    from haac.git_ctx import GitContext
    from haac.config import Config

    # haac touched this one
    (repo / "state").mkdir()
    (repo / "state" / "entities.yaml").write_text("haac_id: x\n")

    # unrelated modification — must NOT be committed
    (repo / "unrelated.txt").write_text("user work")
    subprocess.run(["git", "-C", str(repo), "add", "unrelated.txt"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "user"], check=True)
    (repo / "unrelated.txt").write_text("user work in progress")

    config = Config(ha_url="x", ha_token="t", state_dir=repo / "state", project_dir=repo)
    touched = {Path("state/entities.yaml")}

    _do_auto_commit(config, touched, "haac: apply — test", mode="yes")

    # Check commit happened
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "haac: apply — test" in log

    # unrelated.txt should still be uncommitted
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "unrelated.txt" in status
```

- [ ] **Step 2: Run to confirm failure**

Run: `uv run pytest tests/test_auto_commit.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `_do_auto_commit` in cli.py**

```python
def _do_auto_commit(config, touched_paths: set[Path], suggested_message: str, mode: str) -> None:
    """mode: 'prompt' | 'yes' | 'no'."""
    from haac.git_ctx import GitContext

    if mode == "no" or not touched_paths:
        return
    git_ctx = GitContext(config.project_dir)
    if not git_ctx.is_repo():
        return

    # Filter to paths that actually differ
    real_changes = sorted([p for p in touched_paths if git_ctx.differs_from_head(p)])
    if not real_changes:
        return

    if mode == "prompt":
        if not sys.stdin.isatty():
            return
        console.print("\n[bold]Commit the following files?[/bold]")
        for p in real_changes:
            console.print(f"  {p.as_posix()}")
        console.print(f"\nSuggested message:\n  {suggested_message}")
        answer = input("\n[E]dit message, [Y]es with suggested, [n]o: ").strip().lower()
        if answer == "n":
            return
        if answer == "e":
            suggested_message = input("Message: ").strip() or suggested_message

    # Warn about unrelated uncommitted changes (not fatal)
    status = _unrelated_dirty(git_ctx, touched_paths)
    if status:
        console.print(f"[yellow]Note: you have uncommitted changes in "
                      f"{', '.join(p.as_posix() for p in status)} — not included in this commit.[/yellow]")

    git_ctx.add(real_changes)
    git_ctx.commit(suggested_message)
    console.print(f"[green]Committed {len(real_changes)} files.[/green]")


def _unrelated_dirty(git_ctx, touched_paths: set[Path]) -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(git_ctx.root), "status", "--porcelain"],
        capture_output=True, text=True, check=True,
    )
    dirty = []
    for line in result.stdout.splitlines():
        p = Path(line[3:].strip())
        if p not in touched_paths:
            dirty.append(p)
    return dirty
```

Add `import subprocess` at the top of `cli.py` if not already present.

- [ ] **Step 4: Build suggested message**

In `src/haac/cli.py`, add:

```python
def _suggested_commit_message(plan) -> str:
    renames = [c for r in plan.results for c in r.changes if c.action == "rename"]
    other = [c for r in plan.results for c in r.changes if c.action != "rename"]
    if not renames and not other:
        return "haac: apply — no changes"
    if renames and not other:
        if len(renames) == 1:
            return f"haac: apply — rename {renames[0].name}"
        lines = "\n".join(f"  {c.name}" for c in renames)
        return f"haac: apply — renames:\n{lines}"
    if renames:
        lines = "\n".join(f"  {c.name}" for c in renames)
        return f"haac: apply — renames:\n{lines}\n+{len(other)} other changes"
    return f"haac: apply — {len(other)} changes"
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/test_auto_commit.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/haac/cli.py tests/test_auto_commit.py
git commit -m "feat: scoped auto-commit with per-path filtering"
```

---

### Task 18: Wire auto-commit into `_run_apply`

**Files:**
- Modify: `src/haac/cli.py`

- [ ] **Step 1: Track touched paths through apply flow**

Update `_run_apply` in `src/haac/cli.py`:

```python
async def _run_apply(config, rename_refs_mode="prompt", commit_mode="prompt"):
    touched_paths: set[Path] = set()

    plan = await _plan_once(config)
    rename_changes = [
        (r.provider_name, c) for r in plan.results for c in r.changes if c.action == "rename"
    ]
    if rename_changes and rename_refs_mode != "no":
        paths = await _handle_rename_refs_tracked(config, rename_changes, rename_refs_mode)
        touched_paths.update(paths)
        if paths:
            console.print("\n[bold]Re-planning with updated references...[/bold]")
            plan = await _plan_once(config)

    print_warnings(plan.warnings)

    any_changes = False
    async with HAClient(config.ha_url, config.ha_token) as client:
        providers = get_providers()
        context = await _build_context(providers, client, config)

        for provider in providers:
            if not provider.has_state_file(config.state_dir):
                continue
            desired = context.get(f"desired_{provider.name}", [])
            current = context.get(provider.name, [])
            result = provider.diff(desired, current, context)

            if result.changes:
                any_changes = True
                console.print(f"\n[bold]{result.provider_name.title()}:[/bold]")
                for change in result.changes:
                    await provider.apply_change(client, change)
                    print_apply_change(change)
                context[provider.name] = await provider.read_current(client)

        if any_changes:
            # haac_id backfills may have happened during pull; mark state files if differ
            for p in providers:
                if p.has_state_file(config.state_dir):
                    rel = (config.state_dir / p.state_file).relative_to(config.project_dir)
                    touched_paths.add(rel)
            console.print("\n[bold green]Done.[/bold green]")
        elif not touched_paths:
            console.print("[green]No changes needed — HA matches desired state.[/green]")

    if touched_paths and commit_mode != "no":
        _do_auto_commit(config, touched_paths, _suggested_commit_message(plan), commit_mode)
```

- [ ] **Step 2: Refactor `_handle_rename_refs` to return touched paths**

Update `_handle_rename_refs` — rename to `_handle_rename_refs_tracked` and return `set[Path]` instead of `bool`:

```python
async def _handle_rename_refs_tracked(config, rename_changes, mode: str) -> set[Path]:
    from haac.git_ctx import GitContext
    from haac.rename_refs import scan_references, rewrite_references
    from haac.output import print_ref_preview

    touched: set[Path] = set()
    git_ctx = GitContext(config.project_dir)
    if not git_ctx.is_repo():
        return touched

    for provider_name, change in rename_changes:
        old_id = change.ha_id
        new_id = change.data.get("new_entity_id") or change.data.get("new_id") or change.data.get("name")
        if not old_id or not new_id:
            continue

        if mode == "prompt":
            if not sys.stdin.isatty():
                continue
            console.print(f"\n[bold]Detected rename:[/bold] {old_id} → {new_id}")
            answer = input("Search for references in the repo? [Y/n] ").strip().lower()
            if answer and answer != "y":
                continue

        hits = scan_references(git_ctx, old_id)
        if not hits:
            console.print(f"  [dim]No references found for {old_id}.[/dim]")
            continue

        print_ref_preview(old_id, new_id, hits)

        if mode == "prompt":
            answer = input(f"\nRewrite {len(hits)} references? [y/N] ").strip().lower()
            if answer != "y":
                continue
        elif mode == "no":
            continue

        try:
            changed = rewrite_references(git_ctx, old_id, new_id)
            for p in changed:
                touched.add(p)
            console.print(f"  [green]Rewrote {len(changed)} files.[/green]")
        except Exception as e:
            console.print(f"  [red]Rewrite failed: {e}[/red]")

    return touched
```

- [ ] **Step 3: Run tests**

Run: `uv run pytest tests/ -v`
Expected: All pass (update `test_handle_rename_refs_yes_mode_rewrites` to expect the set-of-paths return).

- [ ] **Step 4: Commit**

```bash
git add src/haac/cli.py tests/test_rename_refs_flow.py
git commit -m "feat: apply invokes auto-commit with scoped touched paths"
```

---

### Task 19: CLI flags for auto-commit + final integration test

**Files:**
- Modify: `src/haac/cli.py`
- Modify: `tests/test_auto_commit.py`

- [ ] **Step 1: Add argparse flags**

Extend the `apply` parser:

```python
apply_parser.add_argument("--no-commit", action="store_true")
apply_parser.add_argument("--yes-commit", action="store_true")
```

And dispatch:

```python
def _commit_mode(args) -> str:
    if args.yes_commit:
        return "yes"
    if args.no_commit:
        return "no"
    return "prompt"

# in main:
elif args.command == "apply":
    asyncio.run(_run_apply(
        config,
        rename_refs_mode=_refs_mode(args),
        commit_mode=_commit_mode(args),
    ))
```

- [ ] **Step 2: Add end-to-end test**

Append to `tests/test_auto_commit.py`:

```python
def test_auto_commit_skipped_when_no_touched_paths(repo):
    from haac.cli import _do_auto_commit
    from haac.config import Config

    config = Config(ha_url="x", ha_token="t", state_dir=repo / "state", project_dir=repo)
    _do_auto_commit(config, set(), "msg", mode="yes")
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "msg" not in log


def test_auto_commit_no_mode_skips(repo):
    from haac.cli import _do_auto_commit
    from haac.config import Config

    (repo / "a.yaml").write_text("x")
    config = Config(ha_url="x", ha_token="t", state_dir=repo, project_dir=repo)
    _do_auto_commit(config, {Path("a.yaml")}, "msg", mode="no")
    log = subprocess.run(
        ["git", "-C", str(repo), "log", "--format=%s"],
        capture_output=True, text=True, check=True,
    ).stdout
    assert "msg" not in log
```

- [ ] **Step 3: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add src/haac/cli.py tests/test_auto_commit.py
git commit -m "feat: --no-commit / --yes-commit flags on apply"
```

---

## Self-Review

### Spec coverage

- ✅ Section 1 (`haac_id` identity): Tasks 2, 4, 5, 6
- ✅ Section 2 (rename detection via git): Tasks 1, 3, 8–12
- ✅ Section 3 (`Change.rename`): Task 7
- ✅ Section 4 (per-provider renames): Tasks 8, 9, 10, 11
- ✅ Section 5 (auto-rename references): Tasks 14, 15, 16
- ✅ Section 6 (auto-commit): Tasks 17, 18, 19
- ✅ Section 7 (error handling): covered inline in Tasks 14 (pre-check writability + rollback), 11 (POST-before-DELETE for automations/scenes)
- ⚠ Testing section: new test files in every task — covered.
- ⚠ CLI flags summary: Task 15 adds `--no/yes-rename-refs`; Task 19 adds `--no/yes-commit`.

### Type consistency check

- `GitContext.head_blob(Path)` — used consistently in Tasks 1, 3, 8, 10, 11, 14, 17.
- `_ensure_haac_id(list[dict])` — Tasks 2, 4, 6.
- `git_head_entry(git_ctx, state_file, root_key, haac_id)` — Tasks 3, 8, 10, 11.
- `_try_detect_rename` — Tasks 8, 9.
- `Change.action in {"create", "update", "rename"}` — Task 7, used in 8–11, 15.
- `scan_references(git_ctx, needle) -> list[RefHit]` — Tasks 14, 15, 17.
- `rewrite_references(git_ctx, old, new) -> list[Path]` — Tasks 14, 17.

All consistent.

### Known simplifications

- `_try_detect_rename` currently only handles providers keyed by `name`. Entities (keyed by `entity_id`) and automations/scenes (keyed by `id`) implement rename detection inline rather than through the helper — pragmatic for a first cut. If more providers follow the name-keyed pattern, extract a broader helper later.
- Some provider `diff` rewrites are described narratively (Task 11 for automations/scenes) because I haven't read those files in detail — the engineer should read them before editing and integrate the rename branch in the appropriate place. The test assertions bound the expected behavior.

### Open items the engineer must verify during implementation

- Exact signature of `HAClient.rest_post` / `rest_delete` in `src/haac/client.py` (Task 11).
- Whether `Config` already carries `project_dir` or needs adding (Task 12).
- HA API support for `label_id` / `area_id` / `floor_id` mutability — if unsupported, rename for those providers degrades to name-only update (design section 4 allows this).
