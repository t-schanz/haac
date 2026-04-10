# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`haac` (Home Assistant as Code) — a standalone Python CLI tool published on PyPI. Manages Home Assistant configuration declaratively via the HA WebSocket and REST APIs.

## Commands

```bash
uv sync                        # install deps
uv run pytest tests/ -v        # run all tests (128 tests)
uv run haac --help             # CLI usage
```

## Architecture

Provider-based resource system. Each HA resource type (floors, areas, automations, etc.) is a provider that implements a common interface.

```
src/haac/
  cli.py              # Entry point: haac plan|apply|pull|delete|init|fetch
  config.py           # Load haac.yaml + .env
  client.py           # HAClient: async WebSocket + REST
  models.py           # Change, PlanResult, Unmanaged dataclasses
  output.py           # Rich console output
  init.py             # Interactive project setup
  providers/
    __init__.py        # Provider ABC + registry
    floors.py          # WebSocket: config/floor_registry/*
    labels.py          # WebSocket: config/label_registry/*
    areas.py           # WebSocket: config/area_registry/* (depends on floors)
    devices.py         # WebSocket: config/device_registry/* (glob pattern matching)
    entities.py        # WebSocket: config/entity_registry/* (name/icon customization)
    automations.py     # REST: /api/config/automation/config/*
    scenes.py          # REST: /api/config/scene/config/*
    helpers.py         # WebSocket: input_boolean/*
    dashboard.py       # WebSocket: lovelace/config*
```

### Provider interface

Every provider implements: `read_desired`, `read_current`, `diff`, `apply_change`, `delete`, `pull`, `write_desired`. Providers register themselves at module import via `register()`.

### Resource matching

Resources are matched by **name** (case-insensitive), not by ID. IDs in state files are internal references. HA auto-generates its own IDs. Exception: automations and scenes match by explicit `id` field.

### Dependency order

Providers apply in order: floors → labels → areas → devices → entities → helpers → automations → scenes → dashboard. Earlier providers' current state is passed via `context` dict to dependent providers.

## Conventions

- `src/haac/` layout with hatchling build backend
- Tests in `tests/` — one test file per provider, 128+ tests
- Async throughout (websockets + httpx)
- Pydantic for config models, dataclasses for diff results
- Rich for terminal output
- No runtime state — all state comes from YAML files + HA API

## Adding a new provider

1. Create `src/haac/providers/new_thing.py` following any existing provider
2. Implement the Provider interface
3. Call `register(NewThingProvider())` at module level
4. Import in `cli.py` to trigger registration
5. Add tests in `tests/test_new_thing.py`

## Publishing

```bash
uv build
uv publish     # or: twine upload dist/*
```
