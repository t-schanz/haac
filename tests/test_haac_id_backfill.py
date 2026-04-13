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
