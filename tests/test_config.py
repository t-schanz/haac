import pytest
from pathlib import Path
from haac.config import load_config, HaacConfig


def test_load_config_defaults(tmp_path):
    config = load_config(tmp_path)
    assert config.state_dir == tmp_path / "state"
    assert config.entities_dir == tmp_path / "entities"
    assert config.ha_url == ""


def test_load_config_from_yaml(tmp_path):
    (tmp_path / "haac.yaml").write_text('ha_url: "http://myha:8123"\n')
    config = load_config(tmp_path)
    assert config.ha_url == "http://myha:8123"


def test_load_config_path_overrides(tmp_path):
    (tmp_path / "haac.yaml").write_text(
        'ha_url: "http://myha:8123"\nstate_dir: ./custom/state\n'
    )
    config = load_config(tmp_path)
    assert config.state_dir == tmp_path / "custom" / "state"


def test_load_config_token_from_env(tmp_path, monkeypatch):
    monkeypatch.setenv("HA_TOKEN", "test-token-123")
    config = load_config(tmp_path)
    assert config.ha_token == "test-token-123"
