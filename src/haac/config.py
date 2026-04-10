"""Load haac.yaml + .env configuration."""

import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel


class HaacConfig(BaseModel):
    ha_url: str = ""
    ha_token: str = ""
    state_dir: Path = Path("state")
    entities_dir: Path = Path("entities")
    project_dir: Path = Path(".")


def load_config(project_dir: Path | None = None) -> HaacConfig:
    project_dir = Path(project_dir or Path.cwd()).resolve()
    load_dotenv(project_dir / ".env")

    config_path = project_dir / "haac.yaml"
    raw = {}
    if config_path.exists():
        raw = yaml.safe_load(config_path.read_text()) or {}

    state_dir = project_dir / raw.get("state_dir", "state")
    entities_dir = project_dir / raw.get("entities_dir", "entities")

    return HaacConfig(
        ha_url=raw.get("ha_url", ""),
        ha_token=os.environ.get("HA_TOKEN", ""),
        state_dir=state_dir,
        entities_dir=entities_dir,
        project_dir=project_dir,
    )
