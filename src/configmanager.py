import os
import json

# Paths inside the config that should have ~ expanded and separators normalised.
_PATH_KEYS = ("default_download_folder", "default_log_folder", "default_cookies_file")

# Anchored to the project root (the parent of src/), NOT to the working
# directory. Resolving this relative to the CWD used to make the whole config
# silently vanish whenever the tool was launched from anywhere but the repo.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def config_search_paths() -> list:
    """
    Config locations in priority order:

    1. <project root>/.config/config.json   — the config shipped with the repo
    2. $XDG_CONFIG_HOME/ytdownload/config.json
    3. ~/.config/ytdownload/config.json     — per-user override (Linux/macOS)
    4. %APPDATA%/ytdownload/config.json     — per-user override (Windows)
    """
    paths = [os.path.join(_PROJECT_ROOT, ".config", "config.json")]

    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        paths.append(os.path.join(xdg_config_home, "ytdownload", "config.json"))

    paths.append(os.path.join(os.path.expanduser("~"), ".config", "ytdownload", "config.json"))

    appdata = os.environ.get("APPDATA")
    if appdata:
        paths.append(os.path.join(appdata, "ytdownload", "config.json"))

    return paths


def _expand_paths(config: dict) -> dict:
    for key in _PATH_KEYS:
        if key in config and isinstance(config[key], str):
            config[key] = os.path.normpath(os.path.expanduser(config[key]))
    return config


def load_config() -> dict:
    """
    Load configuration from the first existing location in config_search_paths().

    Returns {} if no config is found, or if the first one found is unreadable —
    the caller then falls back to its built-in defaults.
    """
    for path in config_search_paths():
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                return _expand_paths(json.load(f))
        except Exception as exc:
            print(f"[WARNING] Failed to read config at {path}: {exc}. Using defaults.")
            return {}

    return {}
