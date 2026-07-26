import os
import json
import pytest
from src import configmanager


def _write_config(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


# Returns empty dict if no config exists anywhere
def test_no_config(monkeypatch, tmp_path):
    monkeypatch.setattr(configmanager, "config_search_paths",
                        lambda: [str(tmp_path / "nope" / "config.json")])
    assert configmanager.load_config() == {}


# Loads the project-root config and expands ~ in path keys
def test_project_config(monkeypatch, tmp_path):
    cfg = tmp_path / ".config" / "config.json"
    _write_config(cfg, {
        "default_download_folder": "~/downloads",
        "default_log_folder": "~/logs",
        "default_segments": 16,
    })
    monkeypatch.setattr(configmanager, "config_search_paths", lambda: [str(cfg)])

    config = configmanager.load_config()
    home = os.path.expanduser("~")
    assert config["default_download_folder"] == os.path.normpath(os.path.join(home, "downloads"))
    assert config["default_log_folder"] == os.path.normpath(os.path.join(home, "logs"))
    assert config["default_segments"] == 16


# Windows-style ~\ paths are expanded and normalised too
def test_windows_style_paths(monkeypatch, tmp_path):
    cfg = tmp_path / ".config" / "config.json"
    _write_config(cfg, {"default_download_folder": "~\\videos"})
    monkeypatch.setattr(configmanager, "config_search_paths", lambda: [str(cfg)])
    monkeypatch.setattr(configmanager.os.path, "expanduser",
                        lambda p: p.replace("~", str(tmp_path)))

    config = configmanager.load_config()
    assert os.path.normpath(config["default_download_folder"]) == \
        os.path.normpath(str(tmp_path / "videos"))


# Earlier paths in the search order win
def test_search_order_prefers_first(monkeypatch, tmp_path):
    first = tmp_path / "first" / "config.json"
    second = tmp_path / "second" / "config.json"
    _write_config(first, {"default_segments": 1})
    _write_config(second, {"default_segments": 2})
    monkeypatch.setattr(configmanager, "config_search_paths",
                        lambda: [str(first), str(second)])

    assert configmanager.load_config()["default_segments"] == 1


# A missing earlier path falls through to a later one
def test_falls_through_to_later_path(monkeypatch, tmp_path):
    missing = tmp_path / "missing" / "config.json"
    present = tmp_path / "present" / "config.json"
    _write_config(present, {"default_segments": 7})
    monkeypatch.setattr(configmanager, "config_search_paths",
                        lambda: [str(missing), str(present)])

    assert configmanager.load_config()["default_segments"] == 7


# Handles invalid JSON gracefully
def test_invalid_json(monkeypatch, tmp_path):
    cfg = tmp_path / ".config" / "config.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{invalid_json", encoding="utf-8")
    monkeypatch.setattr(configmanager, "config_search_paths", lambda: [str(cfg)])

    assert configmanager.load_config() == {}


# --- Regression: the config must not depend on the current working directory ---

def test_project_root_path_is_absolute_and_outside_src():
    """The first search path is the repo's own .config/config.json."""
    first = configmanager.config_search_paths()[0]
    assert os.path.isabs(first)
    # Must be <project root>/.config/config.json, not <project root>/src/.config/...
    assert os.path.basename(os.path.dirname(os.path.dirname(first))) != "src"
    assert first.endswith(os.path.join(".config", "config.json"))


def test_config_loads_from_any_cwd(monkeypatch, tmp_path):
    """
    Regression for the CWD-relative lookup: load_config() previously returned {}
    unless the process happened to be started from the project root.
    """
    if not os.path.exists(configmanager.config_search_paths()[0]):
        pytest.skip("no project config.json checked out")

    monkeypatch.chdir(tmp_path)
    assert configmanager.load_config() != {}
