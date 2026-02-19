import argparse
import sys
import os
import json
import loggingtool
import downloadtool
import configmanager

def get_link_from_user() -> str:
    """Prompt the user to enter a YouTube URL if not provided as a flag."""
    return input("Enter YouTube video URL: ").strip()

def main():
    # Load config
    config = configmanager.load_config()

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