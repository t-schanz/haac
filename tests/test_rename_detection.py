"""Tests for rename detection across providers."""
import subprocess
from pathlib import Path

import pytest

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
