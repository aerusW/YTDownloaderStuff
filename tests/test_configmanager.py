import os
import json
import pytest
from src import configmanager 


# Returns empty dict if no config exists
def test_no_config(tmp_path, monkeypatch):
    # Make sure no config files exist
    monkeypatch.setattr(configmanager.os.path, "exists", lambda path: False)
    config = configmanager.load_config()
    assert config == {}

# Loads script folder config (Windows-style)
def test_script_folder_config(tmp_path, monkeypatch):
    # Create a fake config file in "script folder"
    fake_config_path = tmp_path / ".config" / "config.json"
    fake_config_path.parent.mkdir()
    data = {
        "default_download_folder": "~/downloads",
        "default_log_folder": "~/logs"
    }
    fake_config_path.write_text(json.dumps(data))

    # Monkeypatch __file__ to tmp_path/script.py
    monkeypatch.setattr(configmanager, "__file__", str(tmp_path / "script.py"))

    config = configmanager.load_config()
    # Paths should be expanded
    home = os.path.expanduser("~")
    assert config["default_download_folder"] == os.path.join(home, "downloads")
    assert config["default_log_folder"] == os.path.join(home, "logs")

# Loads home config (Linux/macOS-style)
def test_home_config(tmp_path, monkeypatch):
    # 1. Create the .config SUBFOLDER that the code expects
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    fake_home_config = config_dir / "config.json"
    
    # 2. Write config with ~ paths (Windows-style) to test expansion and normalization
    data = {
        "default_download_folder": "~\\videos",
        "default_log_folder": "~\\videos\\.DownloadLogs"
    }
    fake_home_config.write_text(json.dumps(data))

    # 3. Mock __file__ so the FIRST check (script folder) fails
    monkeypatch.setattr(configmanager, "__file__", str(tmp_path / "script.py"))

    # 4. Mock expanduser to map ~ to our tmp_path
    monkeypatch.setattr(configmanager.os.path, "expanduser", lambda path: path.replace("~", str(tmp_path)))

    # 5. The Critical Fix: Mock exists to recognize the .config subfolder
    def fake_exists(path):
        # We need to recognize ".config/config.json" relative to execution
        return ".config" in path and "config.json" in path

    monkeypatch.setattr(configmanager.os.path, "exists", fake_exists)

    # 6. Run the function
    config = configmanager.load_config()

    # 7. Assertions
    # Note: os.path.join handles the backslashes from your JSON
    expected_path = os.path.normpath(str(tmp_path / "videos"))
    assert os.path.normpath(config["default_download_folder"]) == expected_path

# Handles invalid JSON gracefully
def test_invalid_json(tmp_path, monkeypatch):
    fake_config_path = tmp_path / ".config" / "config.json"
    fake_config_path.parent.mkdir()
    fake_config_path.write_text("{invalid_json")

    monkeypatch.setattr(configmanager, "__file__", str(tmp_path / "script.py"))

    config = configmanager.load_config()
    assert config == {}