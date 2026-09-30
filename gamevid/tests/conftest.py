import pytest

from app import config


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    """Every test gets its own projects/ and data/ folders."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    monkeypatch.setattr(config, "MUSIC_DIR", tmp_path / "music")
    config.ensure_dirs()
    return tmp_path
