# Design: Stable `haac_id` and Rename Support

## Problem

Resources managed by haac (entities, areas, automations, scenes, etc.) are keyed by their Home Assistant identifier — `entity_id`, `area_id`, automation `id`. When a user wants to rename one of these (e.g. `switch.smart_plug_mini` → `switch.smart_plug_tv`), haac has no way to know the two are the same resource. The renamed entry looks like "a desired resource that doesn't exist in HA" and the original looks "unmanaged". There is no rename path, and no mechanism to update the references in scenes, automations, and dashboards that point to the old ID.

Renaming HA IDs is common (devices integrated with auto-generated names, `smart_plug_mini` → a human-friendly name after assignment to a room). Today this is impossible via haac.

## Solution

Add a persistent, haac-generated UUID (`haac_id`) to every managed YAML entry. This becomes the stable identity across runs; HA-side IDs become mutable. Rename detection compares the working-tree YAML against `git show HEAD:<state_file>`: same `haac_id`, different HA ID = rename. On detection, haac emits a rename change, offers to auto-rewrite references elsewhere in the repo, and prompts for a scoped git commit after apply.

Scope: all providers except `devices`/`assignments.yaml` (which is rule-based, not entry-based).

## Detailed Design

### 1. `haac_id` field

Every entry in `state/*.yaml` (except `assignments.yaml`) gains a `haac_id: <uuid4>` field, written as the first key in each entry for readability.

```yaml
---
entities:
  - haac_id: 9f3d4a2e-1c6b-4a8f-b0d7-9e2c1a3b5d8f
    entity_id: switch.smart_plug_tv
    friendly_name: TV Power Strip
```

**Backfill.** On every `pull`, providers scan the desired list for entries missing `haac_id` and assign fresh UUIDs before writing. Idempotent: a second pull makes no changes.

**Matching rule.** `haac_id` is identity across runs and the filesystem; HA knows nothing about it. So matching stays keyed on HA ID, but `haac_id` is what lets us detect a rename:

1. For each desired entry `{haac_id: U, ha_id: Y}`, look up the HA resource with ID = Y. If found → compare fields, emit update if needed. Done.
2. If HA has no resource with ID = Y, look up `haac_id: U` in `git show HEAD:<state_file>`. Say HEAD's entry was `{haac_id: U, ha_id: X}`. If HA has a resource with ID = X, emit a rename change (old = X, new = Y).
3. If HEAD lacks `haac_id: U` (new entry) or HA lacks both X and Y (unmanaged external change), skip with a warning.

**Providers touched.** `floors`, `labels`, `areas`, `entities`, `automations`, `scenes`, `helpers`, `dashboard`. Each gets:

- `pull` backfills `haac_id`.
- `read_desired` preserves it.
- `diff` matches on `haac_id` and detects rename via git.
- `apply_change` sends the provider-specific rename API call.

**`devices`/`assignments.yaml` unchanged** — glob-pattern rules don't represent individual HA resources.

### 2. Rename detection via git

A single helper module wraps git access:

```python
# src/haac/git_ctx.py
class GitContext:
    def is_repo(self) -> bool: ...
    def head_blob(self, path: Path) -> str | None: ...  # returns None if no HEAD or path not tracked
    def ls_files(self) -> list[Path]: ...
    def add(self, paths: list[Path]) -> None: ...
    def commit(self, message: str) -> None: ...
```

A helper `git_head_entry(state_file: Path, haac_id: str) -> dict | None` parses `head_blob` output and returns the matching entry. Cached per-file per-invocation to avoid repeated subprocess calls.

**Rename detection algorithm** (restated from section 1 for clarity):

1. Desired entry `{haac_id: U, ha_id: Y}` has no HA counterpart under ID = Y.
2. Look up `haac_id: U` in HEAD's version of the state file.
3. If HEAD has an entry `{haac_id: U, ha_id: X}` with X ≠ Y, and HA has a resource with ID = X → emit rename (X → Y).
4. If HEAD lacks `haac_id: U` (new entry) or HA lacks both X and Y (renamed outside haac) → skip with warning.

**Fallbacks:**

- **Not a git repo:** rename detection disabled; log once per run. Behavior reverts to today's (desired resource missing → unmanaged on old side, skip on new side).
- **File not in HEAD** (fresh init): same as above.
- **Entry has no `haac_id` in HEAD** (first run after backfill): same as above.

### 3. `Change` action: `rename`

`models.Change.action` gains a new value `"rename"`. A rename change carries both old and new HA IDs. If other fields changed in the same revision (e.g. `friendly_name` also changed), they're bundled into the same `Change` for a single atomic API call where the provider's API allows it.

Plan output:

```
Entities:
  ~ rename entity "switch.smart_plug_mini" → "switch.smart_plug_tv"
      friendly_name: Smart Plug Mini → TV Power Strip
```

### 4. Per-provider rename implementations

| Provider | Rename mechanism |
|---|---|
| entities | `config/entity_registry/update` with `new_entity_id` |
| areas | `config/area_registry/update` — verify HA accepts `area_id` change during implementation; if not, areas are name-keyed and rename is a name update |
| floors | `config/floor_registry/update` — verify `floor_id` mutability during implementation |
| labels | `config/label_registry/update` — verify `label_id` mutability during implementation |
| helpers | `input_boolean/update` — verify `object_id` mutability during implementation |
| automations | REST: POST new-ID config, then DELETE old-ID |
| scenes | REST: POST new-ID config, then DELETE old-ID |
| dashboard | Single resource — rename not supported; skip |

The "verify during implementation" providers ship rename support only if HA's API actually allows changing the ID. If not, that provider's rename is documented as unsupported and treated like a name-only update.

**Automations/scenes two-step.** HA's REST API has no atomic rename for config-stored automations/scenes. Strategy: POST new-ID first; only DELETE old-ID if POST succeeded. If POST fails, abort before DELETE — old remains, no drift. If DELETE fails after successful POST, log the error and continue; user must clean up the duplicate manually. Plan output for automation/scene renames displays both operations explicitly so users can see the risk.

### 5. Auto-rename references

When `plan` or `apply` detects at least one rename change, after printing the plan, interactively prompt:

```
Detected 1 rename: switch.smart_plug_mini → switch.smart_plug_tv

Search for references in the repo? [Y/n]
```

**Scan.** Uses `GitContext.ls_files()` to respect `.gitignore`. Skips `haac.yaml`, `.venv/`, `.git/`, binary files. Matches with `re.compile(r"\b" + re.escape(old_ha_id) + r"\b")` — whole-token boundary, dot escaped. Shows:

```
state/automations.yaml
  42: service: switch.turn_on
  43:   target: { entity_id: switch.smart_plug_mini }
entities/scenes.yaml
  18:   switch.smart_plug_mini:
  19:     state: 'on'

2 references in 2 files. Rewrite? [y/N]
```

Default is **No** — destructive across user files, require explicit opt-in after seeing the preview.

**Rewrite.** Text replacement across all matched files. Before writing, pre-check all target files are writable. If any write fails, restore via `git checkout -- <files>` and abort before proceeding to HA calls.

**Re-plan after rewrite.** Print `Re-planning with updated references...` and re-run the plan from scratch so the printed plan reflects reality.

**Plan is side-effectful.** By design. Documented explicitly in the CLI help.

**Flags.**

- `--no-rename-refs` — skip the reference-rewrite prompt; just show renames.
- `--yes-rename-refs` — accept prompts non-interactively (CI).
- Non-tty stdin → defaults to `--no-rename-refs`.

### 6. Auto-commit after apply

After `apply` completes:

1. Collect paths haac touched this run (reference rewrites + state-file backfills). Tracked explicitly in a `TouchedPaths` set maintained during the run.
2. Filter to paths whose contents actually differ from HEAD.
3. If any, prompt:

```
Commit the following files? [Y/n]
  state/entities.yaml
  entities/scenes.yaml

Suggested message:
  haac: apply — rename switch.smart_plug_mini → switch.smart_plug_tv, +2 changes

[E]dit message, [Y]es with suggested, [n]o:
```

4. On `Y`: `GitContext.add(paths)` then `GitContext.commit(message)`. Only the listed paths — no `-a`, no `-u`.
5. On `E`: open `$EDITOR` for the message (fallback: inline multi-line input).
6. On `n`: skip silently.

**Unrelated uncommitted work.** Never touched. If the working tree has modifications in other tracked files, print an advisory:

```
Note: you have uncommitted changes in foo.yaml, bar.yaml — not included in this commit.
```

**Suggested message format.** Built from the run's `Change` list:

- `haac: apply —` prefix.
- Rename changes listed first, one per line if multiple.
- Trailing summary: `+N other changes`.

Example with multiple renames:

```
haac: apply — renames:
  switch.smart_plug_mini → switch.smart_plug_tv
  light.hue_spot_1 → light.living_room_spot_left
+3 other changes
```

**Flags.**

- `--no-commit` / `--yes-commit` on `apply`.
- Non-tty stdin → `--no-commit`.

**No-git case.** Commit step skipped silently.

### 7. Error handling

1. **HA rename call fails.** Repo files untouched; surface error; next run retries.
2. **Reference rewrite fails mid-run.** Pre-check writability of all target files before touching any. If any write fails, `git checkout -- <paths>` to revert, abort before HA calls.
3. **Automation/scene POST succeeds, DELETE fails.** Log error, leave duplicate, continue.
4. **Partial provider failures.** Today's "continue past errors" behavior preserved for non-rename changes. A failed rename short-circuits that provider's remaining changes for the run.
5. **Git prompt declined.** Exit 0. Not an error.

## Testing

New test files:

- `tests/test_haac_id_backfill.py` — pull assigns UUIDs; idempotent; preserves existing IDs.
- `tests/test_rename_detection.py` — mocks real git via tempdir fixtures. Cases: no HEAD, unchanged entry, renamed entry, missing `haac_id` in HEAD, HA missing old ID.
- `tests/test_auto_rename_refs.py` — scans respect `.gitignore`, token boundaries, rewrite idempotence.
- `tests/test_auto_commit.py` — scoped `git add`, working-tree-clean skip, flag interactions.

Per-provider `test_<provider>.py` files gain a rename test exercising each provider's specific HA API call.

**Test strategy:** real git repos in tempdirs rather than mocking subprocess — git's behavior is the contract.

## CLI flags summary

| Flag | Command | Effect |
|---|---|---|
| `--no-rename-refs` | plan, apply | Skip reference-rewrite prompt |
| `--yes-rename-refs` | plan, apply | Auto-accept rewrite prompts |
| `--no-commit` | apply | Skip commit prompt |
| `--yes-commit` | apply | Auto-accept commit prompt with suggested message |

Non-tty stdin defaults to the `--no-*` variants.

## Out of Scope

- Renaming `devices`/`assignments.yaml` rules (not entry-based).
- Renaming the dashboard resource (single-instance).
- Cross-repo reference tracking (other haac projects in the same workspace).
- YAML-semantic-aware rewriting (e.g. recognizing entity_id only in specific keys) — token replacement is sufficient for the common cases.
