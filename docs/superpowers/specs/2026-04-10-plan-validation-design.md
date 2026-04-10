# Design: Inline Validation for `haac plan` and `haac apply`

## Problem

When haac state files contain errors — malformed YAML, missing required fields, or broken cross-references — users get Python tracebacks or silent misbehavior instead of clear, actionable error messages. There is no validation layer between parsing state files and executing diffs/API calls.

### Current failure modes

1. **Malformed YAML** — `yaml.safe_load` throws an unhandled exception; the user sees a traceback.
2. **Wrong structure** — e.g. `floors.yaml` contains a list at the top level instead of `floors: [...]`. `data.get("floors", [])` silently returns `[]`, hiding the user's config.
3. **Missing required fields** — a floor without `name`, an automation without `id`, a device rule without `match`. These blow up with `KeyError` inside `diff()`.
4. **Broken cross-references** — an area references `floor: "ground"` but no floor with `id: "ground"` exists in `floors.yaml`. Currently `_resolve_floor_id` silently returns `None`, and the resource is created/updated with no floor assignment. The user gets no warning.

## Solution

Add validation logic that runs inside the existing `plan` and `apply` flows — no new CLI commands. Validation happens in two phases:

1. **Structure validation** — in each provider's `read_desired`, validate YAML structure and required fields before returning data.
2. **Cross-reference validation** — after all state files are loaded but before diffs run, check that inter-provider references resolve correctly.

Errors are fatal (abort with clear message). Broken cross-references are warnings (shown in plan output, don't block execution).

## Detailed Design

### 1. `HaacConfigError` exception

A new exception class in `models.py`:

```python
class HaacConfigError(Exception):
    """Raised when a state file has invalid structure or content."""
    def __init__(self, file: str, message: str):
        self.file = file
        super().__init__(f"{file}: {message}")
```

`cli.py` catches this at the top level of `_run_plan` and `_run_apply`, prints the error with Rich formatting, and exits with code 1.

### 2. Structure validation in `read_desired`

Each provider validates its parsed YAML in `read_desired`. Validation is provider-specific since each has its own required fields:

| Provider | Root key | Required fields per entry |
|----------|----------|--------------------------|
| floors | `floors` | `name` |
| labels | `labels` | `name` |
| areas | `areas` | `name` |
| devices | `devices` | `match`, `area` |
| entities | `entities` | `entity_id` |
| automations | `automations` | `id` |
| scenes | `scenes` | `id` |
| helpers | `input_booleans` | `name` |
| dashboard | (whole file is the config) | must be a dict; `views` key should be a list |

Validation checks:
- YAML parsed successfully (wrap `yaml.safe_load` to catch `yaml.YAMLError` and re-raise as `HaacConfigError`)
- Root key exists and its value is a list
- Each entry is a dict
- Each entry has all required fields
- Required fields are non-empty strings

Example error messages:
- `floors.yaml: YAML parse error: expected ':', line 3, column 5`
- `floors.yaml: expected a 'floors' key containing a list`
- `floors.yaml: entry #2 is missing required field 'name'`
- `areas.yaml: entry "Kitchen" field 'floor' must be a string, got int`

### 3. Cross-reference validation

A new function `validate_references(desired_state: dict[str, list[dict]]) -> list[ValidationWarning]` that checks:

- **Areas → Floors**: each area's `floor` value (if present) matches an `id` in the floors list
- **Devices → Areas**: each device rule's `area` value matches an `id` in the areas list

This function takes the already-parsed desired state (a dict of provider name to list of entries) and returns a list of warnings. It does not need a HA connection.

Warning model:

```python
@dataclass
class ValidationWarning:
    file: str
    message: str
```

Added to `PlanResult`:

```python
@dataclass
class PlanResult:
    results: list[ProviderResult] = field(default_factory=list)
    warnings: list[ValidationWarning] = field(default_factory=list)
```

### 4. Integration into CLI flow

In `_run_plan` and `_run_apply`:

```
1. Load config
2. Connect to HA
3. For each provider: read_desired (validation happens here — raises on error)
4. validate_references across all desired state (produces warnings)
5. For each provider: read_current, diff, etc. (existing flow)
6. Print warnings before plan output
```

The validation pass in step 3-4 is cheap — it only reads local YAML files and checks in-memory data structures.

### 5. Warning output

Warnings render before the plan/apply output:

```
Warnings:
  ⚠ areas.yaml: "Kitchen" references floor "ground" but no floor with
    id "ground" exists in floors.yaml
  ⚠ assignments.yaml: device rule "hue_*" references area "bedroom" but
    no area with id "bedroom" exists in areas.yaml

Floors:
  + create "Erdgeschoss"
  ...
```

### 6. Where validation lives

- `HaacConfigError` and `ValidationWarning` — in `models.py` alongside existing models
- Structure validation — inline in each provider's `read_desired`
- `validate_references()` — new function in `providers/__init__.py` (it operates on provider data and knows the dependency graph)
- Warning rendering — in `output.py`

## What this does NOT include

- No new CLI command (`validate`, `check`, etc.)
- No JSON schema files — validation is code, tied to what each provider needs
- No offline mode — `plan` still requires HA. Validation just runs first
- No changes to the provider interface — `read_desired` signature unchanged, it just gains internal validation

## Testing

- Unit tests for each provider's `read_desired` with invalid inputs: bad YAML, wrong structure, missing fields
- Unit tests for `validate_references` with broken and valid cross-references
- Integration test that `_run_plan` prints warnings for broken references instead of silently dropping them
- Existing tests continue to pass (they supply valid data)

## Files changed

| File | Change |
|------|--------|
| `src/haac/models.py` | Add `HaacConfigError`, `ValidationWarning`; add `warnings` field to `PlanResult` |
| `src/haac/providers/__init__.py` | Add `validate_references()` function |
| `src/haac/providers/floors.py` | Add validation in `read_desired` |
| `src/haac/providers/labels.py` | Add validation in `read_desired` |
| `src/haac/providers/areas.py` | Add validation in `read_desired` |
| `src/haac/providers/devices.py` | Add validation in `read_desired` |
| `src/haac/providers/entities.py` | Add validation in `read_desired` |
| `src/haac/providers/automations.py` | Add validation in `read_desired` |
| `src/haac/providers/scenes.py` | Add validation in `read_desired` |
| `src/haac/providers/helpers.py` | Add validation in `read_desired` |
| `src/haac/providers/dashboard.py` | Add validation in `read_desired` (dict structure, `views` is a list) |
| `src/haac/cli.py` | Catch `HaacConfigError`, call `validate_references`, pass warnings to output |
| `src/haac/output.py` | Add `print_warnings()` function |
| `tests/test_validation.py` | New test file for validation logic |
