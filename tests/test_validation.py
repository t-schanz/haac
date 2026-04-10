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
