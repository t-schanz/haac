# Inline Validation for `haac plan` and `haac apply` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add clear validation errors and cross-reference warnings to `haac plan` and `haac apply`, replacing tracebacks and silent failures.

**Architecture:** Validation happens in two phases inside the existing plan/apply flow. Phase 1: each provider's `read_desired` validates YAML structure and required fields (raises `HaacConfigError` on failure). Phase 2: a `validate_references` function checks cross-provider links (areas→floors, devices→areas) and returns warnings. No new CLI commands.

**Tech Stack:** Python 3.12, PyYAML, Rich, pytest, pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-10-plan-validation-design.md`

---

## File Structure

| File | Role |
|------|------|
| `src/haac/models.py` | Add `HaacConfigError`, `ValidationWarning`; add `warnings` to `PlanResult` |
| `src/haac/providers/__init__.py` | Add `parse_state_file()` helper and `validate_references()` function |
| `src/haac/providers/floors.py` | Update `read_desired` to use `parse_state_file` |
| `src/haac/providers/labels.py` | Update `read_desired` to use `parse_state_file` |
| `src/haac/providers/areas.py` | Update `read_desired` to use `parse_state_file` |
| `src/haac/providers/devices.py` | Update `read_desired` to use `parse_state_file` |
| `src/haac/providers/entities.py` | Update `read_desired` to use `parse_state_file` |
| `src/haac/providers/automations.py` | Update `read_desired` to use `parse_state_file` |
| `src/haac/providers/scenes.py` | Update `read_desired` to use `parse_state_file` |
| `src/haac/providers/helpers.py` | Update `read_desired` to use `parse_state_file` |
| `src/haac/providers/dashboard.py` | Update `read_desired` with dashboard-specific validation |
| `src/haac/output.py` | Add `print_warnings()` |
| `src/haac/cli.py` | Catch `HaacConfigError`, call `validate_references`, pass warnings through |
| `tests/test_validation.py` | All validation tests |

---

### Task 1: Add models (`HaacConfigError`, `ValidationWarning`, update `PlanResult`)

**Files:**
- Modify: `src/haac/models.py`

- [ ] **Step 1: Add `HaacConfigError` and `ValidationWarning` to models.py**

In `src/haac/models.py`, add before the `Change` class:

```python
class HaacConfigError(Exception):
    """Raised when a state file has invalid structure or content."""
    def __init__(self, file: str, message: str):
        self.file = file
        super().__init__(f"{file}: {message}")


@dataclass
class ValidationWarning:
    file: str
    message: str
```

- [ ] **Step 2: Add `warnings` field to `PlanResult`**

In `src/haac/models.py`, update the `PlanResult` class to add a `warnings` field:

```python
@dataclass
class PlanResult:
    results: list[ProviderResult] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)
```

The existing properties (`has_changes`, `total_creates`, `total_updates`, `total_unmanaged`) remain unchanged.

- [ ] **Step 3: Run existing tests to confirm nothing breaks**

Run: `uv run pytest tests/ -v`
Expected: All 128 tests pass (models are backward-compatible — `warnings` defaults to `[]`).

- [ ] **Step 4: Commit**

```bash
git add src/haac/models.py
git commit -m "feat: add HaacConfigError and ValidationWarning models"
```

---

### Task 2: Add `parse_state_file` helper with tests

**Files:**
- Modify: `src/haac/providers/__init__.py`
- Create: `tests/test_validation.py`

- [ ] **Step 1: Write failing tests for `parse_state_file`**

Create `tests/test_validation.py`:

```python
import pytest
from pathlib import Path

from haac.models import HaacConfigError
from haac.providers import parse_state_file


@pytest.fixture
def tmp_state(tmp_path):
    """Helper: write content to a file and return its path."""
    def _write(filename: str, content: str) -> Path:
        p = tmp_path / filename
        p.write_text(content)
        return p
    return _write


class TestParseStateFile:
    def test_valid_file(self, tmp_state):
        path = tmp_state("floors.yaml", "floors:\n  - name: Ground\n")
        result = parse_state_file(path, "floors", ["name"])
        assert result == [{"name": "Ground"}]

    def test_malformed_yaml(self, tmp_state):
        path = tmp_state("floors.yaml", "floors:\n  - name: Ground\n  bad indentation")
        with pytest.raises(HaacConfigError, match="floors.yaml.*YAML parse error"):
            parse_state_file(path, "floors", ["name"])

    def test_missing_root_key(self, tmp_state):
        path = tmp_state("floors.yaml", "wrong_key:\n  - name: Ground\n")
        with pytest.raises(HaacConfigError, match="floors.yaml.*expected a 'floors' key"):
            parse_state_file(path, "floors", ["name"])

    def test_root_key_not_a_list(self, tmp_state):
        path = tmp_state("floors.yaml", "floors: not_a_list\n")
        with pytest.raises(HaacConfigError, match="floors.yaml.*expected 'floors' to be a list"):
            parse_state_file(path, "floors", ["name"])

    def test_entry_not_a_dict(self, tmp_state):
        path = tmp_state("floors.yaml", "floors:\n  - just a string\n")
        with pytest.raises(HaacConfigError, match="floors.yaml.*entry #1 must be a mapping"):
            parse_state_file(path, "floors", ["name"])

    def test_missing_required_field(self, tmp_state):
        path = tmp_state("floors.yaml", "floors:\n  - icon: mdi:home\n")
        with pytest.raises(HaacConfigError, match="floors.yaml.*entry #1 is missing required field 'name'"):
            parse_state_file(path, "floors", ["name"])

    def test_empty_required_field(self, tmp_state):
        path = tmp_state("floors.yaml", "floors:\n  - name: ''\n")
        with pytest.raises(HaacConfigError, match="floors.yaml.*entry #1 has empty required field 'name'"):
            parse_state_file(path, "floors", ["name"])

    def test_multiple_required_fields(self, tmp_state):
        path = tmp_state("assignments.yaml", "devices:\n  - match: 'hue_*'\n    area: kitchen\n")
        result = parse_state_file(path, "devices", ["match", "area"])
        assert result == [{"match": "hue_*", "area": "kitchen"}]

    def test_null_yaml_content(self, tmp_state):
        path = tmp_state("floors.yaml", "---\n")
        with pytest.raises(HaacConfigError, match="floors.yaml.*expected a 'floors' key"):
            parse_state_file(path, "floors", ["name"])

    def test_empty_list_is_valid(self, tmp_state):
        path = tmp_state("floors.yaml", "floors: []\n")
        result = parse_state_file(path, "floors", ["name"])
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation.py -v`
Expected: FAIL — `ImportError: cannot import name 'parse_state_file'`

- [ ] **Step 3: Implement `parse_state_file`**

In `src/haac/providers/__init__.py`, add after the existing imports:

```python
from haac.models import HaacConfigError


def parse_state_file(path: Path, root_key: str, required_fields: list[str]) -> list[dict]:
    """Parse a YAML state file with structure and field validation.

    Returns the list of entries under root_key.
    Raises HaacConfigError with a clear message on any problem.
    """
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise HaacConfigError(path.name, f"YAML parse error: {e}")

    if not isinstance(data, dict) or root_key not in data:
        raise HaacConfigError(path.name, f"expected a '{root_key}' key containing a list")

    entries = data[root_key]
    if not isinstance(entries, list):
        raise HaacConfigError(path.name, f"expected '{root_key}' to be a list, got {type(entries).__name__}")

    for i, entry in enumerate(entries, 1):
        if not isinstance(entry, dict):
            raise HaacConfigError(path.name, f"entry #{i} must be a mapping, got {type(entry).__name__}")
        for field in required_fields:
            if field not in entry:
                raise HaacConfigError(path.name, f"entry #{i} is missing required field '{field}'")
            if not entry[field] and entry[field] != 0:
                raise HaacConfigError(path.name, f"entry #{i} has empty required field '{field}'")

    return entries
```

Note: `yaml` is already imported at the top of `__init__.py` — just add the `HaacConfigError` import and the function.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation.py -v`
Expected: All 10 tests PASS.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add src/haac/providers/__init__.py tests/test_validation.py
git commit -m "feat: add parse_state_file helper with validation"
```

---

### Task 3: Update all providers to use `parse_state_file`

**Files:**
- Modify: `src/haac/providers/floors.py`
- Modify: `src/haac/providers/labels.py`
- Modify: `src/haac/providers/areas.py`
- Modify: `src/haac/providers/devices.py`
- Modify: `src/haac/providers/entities.py`
- Modify: `src/haac/providers/automations.py`
- Modify: `src/haac/providers/scenes.py`
- Modify: `src/haac/providers/helpers.py`
- Modify: `src/haac/providers/dashboard.py`

Every standard provider follows the same pattern. Replace the raw `yaml.safe_load` + `data.get()` in `read_desired` with a call to `parse_state_file`.

- [ ] **Step 1: Update `floors.py`**

In `src/haac/providers/floors.py`, replace the `read_desired` method:

Old:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("floors", [])
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "floors", ["name"])
```

Also update the import line to add `parse_state_file`:
```python
from haac.providers import Provider, register, parse_state_file
```

The `import yaml` at the top can be removed if it's only used in `read_desired`. Check: `yaml` is not used anywhere else in `floors.py` — remove it.

- [ ] **Step 2: Update `labels.py`**

Same pattern. In `src/haac/providers/labels.py`:

Old `read_desired`:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("labels", [])
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "labels", ["name"])
```

Update import: `from haac.providers import Provider, register, parse_state_file`
Remove: `import yaml`

- [ ] **Step 3: Update `areas.py`**

In `src/haac/providers/areas.py`:

Old `read_desired`:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("areas", [])
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "areas", ["name"])
```

Update import: `from haac.providers import Provider, register, parse_state_file`
Remove: `import yaml`

- [ ] **Step 4: Update `devices.py`**

In `src/haac/providers/devices.py`:

Old `read_desired`:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("devices", [])
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "devices", ["match", "area"])
```

Update import: `from haac.providers import Provider, register, parse_state_file`
Remove: `import yaml`

- [ ] **Step 5: Update `entities.py`**

In `src/haac/providers/entities.py`:

Old `read_desired`:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("entities", [])
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "entities", ["entity_id"])
```

Update import: `from haac.providers import Provider, register, parse_state_file`

Note: `entities.py` still uses `yaml` in `write_desired` (line 78) and `pull` — keep the `import yaml`.

- [ ] **Step 6: Update `automations.py`**

In `src/haac/providers/automations.py`:

Old `read_desired`:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("automations", [])
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "automations", ["id"])
```

Update import: `from haac.providers import Provider, register, parse_state_file`
Remove: `import yaml`

- [ ] **Step 7: Update `scenes.py`**

In `src/haac/providers/scenes.py`:

Old `read_desired`:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("scenes", [])
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "scenes", ["id"])
```

Update import: `from haac.providers import Provider, register, parse_state_file`
Remove: `import yaml`

- [ ] **Step 8: Update `helpers.py`**

In `src/haac/providers/helpers.py`:

Old `read_desired`:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return data.get("input_booleans", [])
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        return parse_state_file(path, "input_booleans", ["name"])
```

Update import: `from haac.providers import Provider, register, parse_state_file`
Remove: `import yaml`

- [ ] **Step 9: Update `dashboard.py`**

Dashboard is special — it's a single config dict, not a list of entries. It doesn't use `parse_state_file`. Instead, add inline validation:

In `src/haac/providers/dashboard.py`, replace `read_desired`:

Old:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        data = yaml.safe_load(path.read_text()) or {}
        return [data]  # wrap in list for consistency
```

New:
```python
    async def read_desired(self, state_dir: Path) -> list[dict]:
        path = state_dir / self.state_file
        if not path.exists():
            return []
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError as e:
            raise HaacConfigError(path.name, f"YAML parse error: {e}")
        if not isinstance(data, dict):
            raise HaacConfigError(path.name, "expected a YAML mapping at the top level")
        if "views" in data and not isinstance(data["views"], list):
            raise HaacConfigError(path.name, "expected 'views' to be a list")
        return [data]
```

Add import: `from haac.models import HaacConfigError` (add `HaacConfigError` to the existing `from haac.models import Change, ProviderResult` line).

- [ ] **Step 10: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All existing tests pass. The existing tests construct provider data directly (they don't go through `read_desired`), so validation doesn't affect them.

- [ ] **Step 11: Commit**

```bash
git add src/haac/providers/
git commit -m "feat: add structure validation to all provider read_desired methods"
```

---

### Task 4: Add `validate_references` with tests

**Files:**
- Modify: `src/haac/providers/__init__.py`
- Modify: `tests/test_validation.py`

- [ ] **Step 1: Write failing tests for `validate_references`**

Append to `tests/test_validation.py`:

```python
from haac.models import ValidationWarning
from haac.providers import validate_references


class TestValidateReferences:
    def test_no_warnings_when_valid(self):
        desired = {
            "floors": [{"id": "ground", "name": "Ground"}],
            "areas": [{"name": "Kitchen", "floor": "ground"}],
            "devices": [{"match": "hue_*", "area": "kitchen_id"}],
        }
        # No areas with id "kitchen_id" — but let's make it valid:
        desired["areas"] = [{"id": "kitchen_id", "name": "Kitchen", "floor": "ground"}]
        warnings = validate_references(desired)
        assert warnings == []

    def test_area_references_missing_floor(self):
        desired = {
            "floors": [{"id": "ground", "name": "Ground"}],
            "areas": [{"name": "Kitchen", "floor": "nonexistent"}],
        }
        warnings = validate_references(desired)
        assert len(warnings) == 1
        assert "Kitchen" in warnings[0].message
        assert "nonexistent" in warnings[0].message
        assert warnings[0].file == "areas.yaml"

    def test_area_without_floor_ref_no_warning(self):
        desired = {
            "floors": [{"id": "ground", "name": "Ground"}],
            "areas": [{"name": "Kitchen"}],
        }
        warnings = validate_references(desired)
        assert warnings == []

    def test_device_references_missing_area(self):
        desired = {
            "areas": [{"id": "kitchen", "name": "Kitchen"}],
            "devices": [{"match": "hue_*", "area": "bedroom"}],
        }
        warnings = validate_references(desired)
        assert len(warnings) == 1
        assert "hue_*" in warnings[0].message
        assert "bedroom" in warnings[0].message
        assert warnings[0].file == "assignments.yaml"

    def test_multiple_warnings(self):
        desired = {
            "floors": [],
            "areas": [
                {"name": "Kitchen", "floor": "missing_floor"},
                {"name": "Bedroom", "floor": "also_missing"},
            ],
            "devices": [{"match": "*", "area": "missing_area"}],
        }
        warnings = validate_references(desired)
        assert len(warnings) == 3

    def test_empty_desired_state(self):
        warnings = validate_references({})
        assert warnings == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validation.py::TestValidateReferences -v`
Expected: FAIL — `ImportError: cannot import name 'validate_references'`

- [ ] **Step 3: Implement `validate_references`**

In `src/haac/providers/__init__.py`, add after `parse_state_file`, and add `ValidationWarning` to the `HaacConfigError` import:

```python
from haac.models import HaacConfigError, ValidationWarning


def validate_references(desired_state: dict[str, list[dict]]) -> list[ValidationWarning]:
    """Check cross-provider references and return warnings for broken links."""
    warnings = []

    floors = desired_state.get("floors", [])
    floor_ids = {f["id"] for f in floors if "id" in f}

    areas = desired_state.get("areas", [])
    area_ids = {a["id"] for a in areas if "id" in a}

    for area in areas:
        floor_ref = area.get("floor")
        if floor_ref and floor_ref not in floor_ids:
            warnings.append(ValidationWarning(
                file="areas.yaml",
                message=f'"{area["name"]}" references floor "{floor_ref}" but no floor with id "{floor_ref}" exists in floors.yaml',
            ))

    devices = desired_state.get("devices", [])
    for rule in devices:
        area_ref = rule.get("area")
        if area_ref and area_ref not in area_ids:
            warnings.append(ValidationWarning(
                file="assignments.yaml",
                message=f'device rule "{rule["match"]}" references area "{area_ref}" but no area with id "{area_ref}" exists in areas.yaml',
            ))

    return warnings
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validation.py -v`
Expected: All tests PASS (both `TestParseStateFile` and `TestValidateReferences`).

- [ ] **Step 5: Commit**

```bash
git add src/haac/providers/__init__.py tests/test_validation.py
git commit -m "feat: add validate_references for cross-provider link checking"
```

---

### Task 5: Add warning output

**Files:**
- Modify: `src/haac/output.py`

- [ ] **Step 1: Add `print_warnings` function**

In `src/haac/output.py`, add the import and function:

Update the import line:
```python
from haac.models import PlanResult, Change, Unmanaged, ValidationWarning
```

Add after the `print_plan` function:

```python
def print_warnings(warnings: list[ValidationWarning]) -> None:
    if not warnings:
        return
    console.print("\n[bold yellow]Warnings:[/bold yellow]")
    for w in warnings:
        console.print(f"  [yellow]⚠[/yellow] {w.file}: {w.message}")
```

- [ ] **Step 2: Update `print_plan` to accept and display warnings**

Modify `print_plan` to call `print_warnings` at the start. Change the signature:

Old:
```python
def print_plan(plan: PlanResult) -> None:
    if not plan.has_changes and plan.total_unmanaged == 0:
```

New:
```python
def print_plan(plan: PlanResult) -> None:
    print_warnings(plan.warnings)

    if not plan.has_changes and plan.total_unmanaged == 0:
```

- [ ] **Step 3: Run existing tests**

Run: `uv run pytest tests/ -v`
Expected: All pass. `print_plan` still works because `PlanResult.warnings` defaults to `[]`.

- [ ] **Step 4: Commit**

```bash
git add src/haac/output.py
git commit -m "feat: add warning output to plan display"
```

---

### Task 6: Wire validation into CLI

**Files:**
- Modify: `src/haac/cli.py`

- [ ] **Step 1: Add `HaacConfigError` import and error handling**

In `src/haac/cli.py`, add to the imports:

```python
from haac.models import PlanResult, HaacConfigError
```

Update `main()` to catch the error. Wrap the plan/apply/pull/delete dispatch in a try/except. Replace the command dispatch block (lines 147-155):

Old:
```python
    if args.command == "plan":
        plan = asyncio.run(_run_plan(config))
        sys.exit(2 if plan.has_changes else 0)
    elif args.command == "apply":
        asyncio.run(_run_apply(config))
    elif args.command == "pull":
        asyncio.run(_run_pull(config))
    elif args.command == "delete":
        asyncio.run(_run_delete(config, args.targets))
```

New:
```python
    try:
        if args.command == "plan":
            plan = asyncio.run(_run_plan(config))
            sys.exit(2 if plan.has_changes else 0)
        elif args.command == "apply":
            asyncio.run(_run_apply(config))
        elif args.command == "pull":
            asyncio.run(_run_pull(config))
        elif args.command == "delete":
            asyncio.run(_run_delete(config, args.targets))
    except HaacConfigError as e:
        console.print(f"[red]Config error:[/red] {e}")
        sys.exit(1)
```

- [ ] **Step 2: Add `validate_references` call to `_run_plan`**

In `_run_plan`, after `_build_context` returns and before the diff loop, collect desired state and validate. Replace the function:

Old:
```python
async def _run_plan(config):
    plan = PlanResult()

    async with HAClient(config.ha_url, config.ha_token) as client:
        providers = get_providers()
        context = await _build_context(providers, client, config)

        for provider in providers:
            if not provider.has_state_file(config.state_dir):
                continue
            desired = context.get(f"desired_{provider.name}", [])
            current = context.get(provider.name, [])
            result = provider.diff(desired, current, context)
            plan.results.append(result)

    print_plan(plan)
    return plan
```

New:
```python
async def _run_plan(config):
    plan = PlanResult()

    async with HAClient(config.ha_url, config.ha_token) as client:
        providers = get_providers()
        context = await _build_context(providers, client, config)

        desired_state = {
            p.name: context[f"desired_{p.name}"]
            for p in providers
            if f"desired_{p.name}" in context
        }
        plan.warnings = validate_references(desired_state)

        for provider in providers:
            if not provider.has_state_file(config.state_dir):
                continue
            desired = context.get(f"desired_{provider.name}", [])
            current = context.get(provider.name, [])
            result = provider.diff(desired, current, context)
            plan.results.append(result)

    print_plan(plan)
    return plan
```

- [ ] **Step 3: Add `validate_references` call to `_run_apply`**

Same pattern for `_run_apply`. Add validation after `_build_context` and print warnings before applying:

Old (after `context = await _build_context(...)`, before the loop):
```python
        any_changes = False
        for provider in providers:
```

New:
```python
        desired_state = {
            p.name: context[f"desired_{p.name}"]
            for p in providers
            if f"desired_{p.name}" in context
        }
        warnings = validate_references(desired_state)
        print_warnings(warnings)

        any_changes = False
        for provider in providers:
```

- [ ] **Step 4: Update imports in `cli.py`**

Add `validate_references` to the providers import:
```python
from haac.providers import get_providers, get_provider, validate_references
```

Add `print_warnings` to the output import:
```python
from haac.output import print_plan, print_apply_change, print_delete, print_pull_add, print_warnings, console
```

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/haac/cli.py
git commit -m "feat: wire validation errors and warnings into plan/apply flow"
```

---

### Task 7: Integration tests for provider `read_desired` validation

**Files:**
- Modify: `tests/test_validation.py`

- [ ] **Step 1: Write integration tests for provider-level validation**

Append to `tests/test_validation.py`:

```python
import asyncio

from haac.providers.floors import FloorsProvider
from haac.providers.labels import LabelsProvider
from haac.providers.areas import AreasProvider
from haac.providers.devices import DevicesProvider
from haac.providers.entities import EntitiesProvider
from haac.providers.automations import AutomationsProvider
from haac.providers.scenes import ScenesProvider
from haac.providers.helpers import HelpersProvider
from haac.providers.dashboard import DashboardProvider


class TestProviderReadDesiredValidation:
    """Verify each provider raises HaacConfigError for invalid state files."""

    def _run(self, coro):
        return asyncio.run(coro)

    def test_floors_missing_name(self, tmp_state):
        path = tmp_state("floors.yaml", "floors:\n  - icon: mdi:home\n")
        p = FloorsProvider()
        with pytest.raises(HaacConfigError, match="missing required field 'name'"):
            self._run(p.read_desired(path.parent))

    def test_labels_missing_name(self, tmp_state):
        path = tmp_state("labels.yaml", "labels:\n  - icon: mdi:tag\n")
        p = LabelsProvider()
        with pytest.raises(HaacConfigError, match="missing required field 'name'"):
            self._run(p.read_desired(path.parent))

    def test_areas_missing_name(self, tmp_state):
        path = tmp_state("areas.yaml", "areas:\n  - floor: ground\n")
        p = AreasProvider()
        with pytest.raises(HaacConfigError, match="missing required field 'name'"):
            self._run(p.read_desired(path.parent))

    def test_devices_missing_match(self, tmp_state):
        path = tmp_state("assignments.yaml", "devices:\n  - area: kitchen\n")
        p = DevicesProvider()
        with pytest.raises(HaacConfigError, match="missing required field 'match'"):
            self._run(p.read_desired(path.parent))

    def test_entities_missing_entity_id(self, tmp_state):
        path = tmp_state("entities.yaml", "entities:\n  - friendly_name: Lamp\n")
        p = EntitiesProvider()
        with pytest.raises(HaacConfigError, match="missing required field 'entity_id'"):
            self._run(p.read_desired(path.parent))

    def test_automations_missing_id(self, tmp_state):
        path = tmp_state("automations.yaml", "automations:\n  - alias: Test\n")
        p = AutomationsProvider()
        with pytest.raises(HaacConfigError, match="missing required field 'id'"):
            self._run(p.read_desired(path.parent))

    def test_scenes_missing_id(self, tmp_state):
        path = tmp_state("scenes.yaml", "scenes:\n  - name: Relax\n")
        p = ScenesProvider()
        with pytest.raises(HaacConfigError, match="missing required field 'id'"):
            self._run(p.read_desired(path.parent))

    def test_helpers_missing_name(self, tmp_state):
        path = tmp_state("helpers.yaml", "input_booleans:\n  - icon: mdi:toggle\n")
        p = HelpersProvider()
        with pytest.raises(HaacConfigError, match="missing required field 'name'"):
            self._run(p.read_desired(path.parent))

    def test_dashboard_not_a_dict(self, tmp_state):
        path = tmp_state("dashboard.yaml", "- view1\n- view2\n")
        p = DashboardProvider()
        with pytest.raises(HaacConfigError, match="expected a YAML mapping"):
            self._run(p.read_desired(path.parent))

    def test_dashboard_views_not_a_list(self, tmp_state):
        path = tmp_state("dashboard.yaml", "views: not_a_list\n")
        p = DashboardProvider()
        with pytest.raises(HaacConfigError, match="expected 'views' to be a list"):
            self._run(p.read_desired(path.parent))

    def test_floors_valid_file_returns_data(self, tmp_state):
        path = tmp_state("floors.yaml", "floors:\n  - name: Ground\n    icon: mdi:home\n")
        p = FloorsProvider()
        result = self._run(p.read_desired(path.parent))
        assert result == [{"name": "Ground", "icon": "mdi:home"}]

    def test_missing_file_returns_empty(self, tmp_path):
        p = FloorsProvider()
        result = self._run(p.read_desired(tmp_path))
        assert result == []
```

- [ ] **Step 2: Run validation tests**

Run: `uv run pytest tests/test_validation.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests pass (existing + new).

- [ ] **Step 4: Commit**

```bash
git add tests/test_validation.py
git commit -m "test: add integration tests for provider read_desired validation"
```
