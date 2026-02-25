import os 
import json
def load_config():
    """
    Load configuration from script folder (Windows) or ~/.config/config.json (Linux/macOS).
    Resolves ~ to home folder.
    """
    # First, try script folder config (Windows)
    script_config_path = os.path.join(os.path.dirname(__file__), ".config/config.json")
    if os.path.exists(script_config_path):
        try:
            with open(script_config_path, "r") as f:
                config = json.load(f)
                # Expand ~ in paths
                for key in ["default_download_folder", "default_log_folder"]:
                    if key in config:
                        config[key] = os.path.expanduser(config[key])
                return config
        except Exception:
            print("[WARNING] Failed to read script folder config. Using defaults.")
            return {}

    # Fallback for Linux/macOS
    config_path = os.path.expanduser(".config/config.json")
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
                for key in ["default_download_folder", "default_log_folder"]:
                    if key in config:
                        config[key] = os.path.expanduser(config[key])
                return config
        except Exception:
            print("[WARNING] Failed to read .config/config.json. Using defaults.")
            return {}

    return {}