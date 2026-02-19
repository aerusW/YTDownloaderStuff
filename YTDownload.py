import argparse
import subprocess
import sys
import os
from tqdm import tqdm # for progress bar 
from yt_dlp import YoutubeDL # for downloading YouTube videos
import re # for regex parsing of aria2 output
from datetime import datetime # for timestamping logs
import json
import loggingtool
import downloadtool

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



def get_link_from_user() -> str:
    """Prompt the user to enter a YouTube URL if not provided as a flag."""
    return input("Enter YouTube video URL: ").strip()

def main():
    # Load config
    config = load_config()

    # Fallback default folder
    home = os.path.expanduser("~")
    fallback_folder = os.path.join(home, "Videos", "DownloadedVideos")

    parser = argparse.ArgumentParser(
        prog="YTDownload",
        description="High-speed YouTube downloader with progress bars and AAC conversion.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--link", type=str, help="YouTube video URL")
    parser.add_argument("--quality", choices=["720", "1080", "4k"], default="1080", help="Maximum video quality")
    parser.add_argument("--folder", type=str, help="Output folder for downloaded videos (overrides config)")
    parser.add_argument("--log-folder", type=str, help="Folder where log files will be stored (overrides config)")

    args = parser.parse_args()

    # Resolve final folders (flag > config > fallback) and make absolute
    final_folder = os.path.abspath(args.folder if args.folder else config.get("default_download_folder", fallback_folder))
    final_log_folder = os.path.abspath(args.log_folder if args.log_folder else config.get("default_log_folder", final_folder))

    # Prompt user for URL if not provided
    url = args.link if args.link else get_link_from_user()
    if not url:
        print("[ERROR] No URL provided.")
        sys.exit(1)

    # Ensure folders exist
    os.makedirs(final_folder, exist_ok=True)
    os.makedirs(final_log_folder, exist_ok=True)

    # Setup logging
    log_file = loggingtool.setup_logging(final_log_folder)

    # Determine next sequential filename
    output_filename = downloadtool.get_next_video_filename(final_folder)

    downloadtool.download_video(url, args.quality, output_filename)

if __name__ == "__main__":
    main()
