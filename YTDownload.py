import argparse
import sys
import os
import loggingtool
import downloadtool
import configmanager
import subprocess

def get_link_from_user() -> str:
    """Prompt the user to enter a YouTube URL if not provided as a flag."""
    return input("Enter YouTube video URL: ").strip()

def check_ffmpeg_installed() -> bool:
    """Check if ffmpeg is installed and available in PATH."""
    try:
        subprocess.run(["ffmpeg", "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except FileNotFoundError:
        return False

def main():
    # Load config
    config = configmanager.load_config()
    # Check for ffmpeg
    if not check_ffmpeg_installed():
        print("[ERROR] ffmpeg is not installed or not found in PATH. Please install ffmpeg to use this tool.")
        sys.exit(1)

    # Fallback default folder
    home = os.path.expanduser("~")
    fallback_folder = os.path.join(home, "Videos", "DownloadedVideos")

    parser = argparse.ArgumentParser(
        prog="YTDownload",
        description="High-speed YouTube downloader with progress bars and AAC conversion.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--link", action="append", type=str, help="YouTube video URL (can be repeated)")
    parser.add_argument("--quality", choices=["720", "1080", "4k"], default="1080", help="Maximum video quality")
    parser.add_argument("--folder", type=str, help="Output folder for downloaded videos (overrides config)")
    parser.add_argument("--log-folder", type=str, help="Folder where log files will be stored (overrides config)")
    parser.add_argument("--segments", type=int, help="Number of segments for aria2 download")
    parser.add_argument("--connections", type=int, help="Number of connections per segment for aria2 download")
    parser.add_argument("--segment-size", type=int, help="Segment size in MB for aria2 download")
    parser.add_argument("--do-not-convert", action="store_true", help="Skip audio conversion to AAC")
    parser.add_argument("--concurrent-segments", type=int, help="Number of concurrent segments for yt-dlp")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output for debugging")

    args = parser.parse_args()

    # Resolve final folders (flag > config > fallback) and make absolute
    final_folder = os.path.abspath(args.folder if args.folder else config.get("default_download_folder", fallback_folder))
    final_log_folder = os.path.abspath(args.log_folder if args.log_folder else config.get("default_log_folder", final_folder))

    # Resolve aria2 settings (flag > config > fallback)
    final_segments = args.segments if args.segments is not None else config.get("default_segments", 16)
    final_connections = args.connections if args.connections is not None else config.get("default_connections", 16)
    final_segment_size = args.segment_size if args.segment_size is not None else config.get("default_segment_size", 4)
    final_concurrent_segments = args.concurrent_segments if args.concurrent_segments is not None else config.get("concurrent_segments", 10)
    # Prompt user for URL if not provided
    urls = args.link if args.link else []

    if not urls:
        url = get_link_from_user()
        if url:
            urls.append(url)
        else:
            print("[ERROR] No URL provided.")
            sys.exit(1)

    # Ensure folders exist
    os.makedirs(final_folder, exist_ok=True)
    os.makedirs(final_log_folder, exist_ok=True)

    # Setup logging
    log_file = loggingtool.setup_logging(final_log_folder)

    for url in urls:
        # Determine next sequential filename
        output_filename = downloadtool.get_next_video_filename(final_folder)
        print(f"[INFO] Downloading: {url}")
        downloadtool.download_video(
            url,
            args.quality,
            output_filename,
            final_segments,
            final_connections,
            final_segment_size,
            final_concurrent_segments,
            skip_conversion=args.do_not_convert,
            verbose=args.verbose
        )
if __name__ == "__main__":
    main()