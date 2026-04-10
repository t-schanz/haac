import asyncio

import pytest
from pathlib import Path

from haac.models import HaacConfigError, ValidationWarning
from haac.providers import parse_state_file, validate_references
from haac.providers.floors import FloorsProvider
from haac.providers.labels import LabelsProvider
from haac.providers.areas import AreasProvider
from haac.providers.devices import DevicesProvider
from haac.providers.entities import EntitiesProvider
from haac.providers.automations import AutomationsProvider
from haac.providers.scenes import ScenesProvider
from haac.providers.helpers import HelpersProvider
from haac.providers.dashboard import DashboardProvider


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



class TestValidateReferences:
    def test_no_warnings_when_valid(self):
        desired = {
            "floors": [{"id": "ground", "name": "Ground"}],
            "areas": [{"id": "kitchen_id", "name": "Kitchen", "floor": "ground"}],
            "devices": [{"match": "hue_*", "area": "kitchen_id"}],
        }
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
