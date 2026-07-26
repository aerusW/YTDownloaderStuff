import argparse
import sys
import os
import src.loggingtool as loggingtool
import src.downloadtool as downloadtool
import src.configmanager as configmanager
import subprocess

version: str = "1.0.2 master"
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
        raise RuntimeError("ffmpeg not found")
        # sys.exit(1)

    # Fallback default folder
    home = os.path.expanduser("~")
    fallback_folder = os.path.join(home, "Videos", "DownloadedVideos")

    parser = argparse.ArgumentParser(
        prog="YTDownload",
        description="High-speed YouTube downloader with progress bars and AAC conversion.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument("--link", action="append", type=str, help="YouTube video URL (can be repeated)")
    parser.add_argument("--quality", choices=["720", "1080", "premium", "4k"], default="1080", help="Video quality. 'premium' targets YouTube's enhanced 1080p (format 616, VP9) saved as MKV — requires cookies from a logged-in Premium account")
    parser.add_argument("--cookies-from-browser", type=str, help="Browser to pull cookies from, e.g. 'firefox' or 'firefox:C:\\path\\to\\profile'. Needed for 'premium' quality and to satisfy YouTube's bot check. Note: Chrome/Edge are blocked by App-Bound Encryption on Windows")
    parser.add_argument("--cookies-file", type=str, help="Path to a Netscape cookies.txt to authenticate with (alternative to --cookies-from-browser; survives uninstalling the browser)")
    parser.add_argument("--js-runtime", type=str, help="JavaScript runtime for YouTube's 'n challenge' (default: deno)")
    parser.add_argument("--folder", type=str, help="Output folder for downloaded videos (overrides config)")
    parser.add_argument("--log-folder", type=str, help="Folder where log files will be stored (overrides config)")
    parser.add_argument("--segments", type=int, help="Number of segments for aria2 download")
    parser.add_argument("--connections", type=int, help="Number of connections per segment for aria2 download")
    parser.add_argument("--segment-size", type=int, help="Segment size in MB for aria2 download")
    parser.add_argument("--do-not-convert", action="store_true", help="Skip audio conversion to AAC")
    parser.add_argument("--concurrent-segments", type=int, help="Number of concurrent segments for yt-dlp")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose output for debugging")
    parser.add_argument("--version", action="version", version=f"%(prog)s {version}")

    args = parser.parse_args()

    # Resolve final folders (flag > config > fallback) and make absolute
    final_folder = os.path.abspath(args.folder if args.folder else config.get("default_download_folder", fallback_folder))
    final_log_folder = os.path.abspath(args.log_folder if args.log_folder else config.get("default_log_folder", final_folder))

    # Resolve aria2 settings (flag > config > fallback)
    final_segments = args.segments if args.segments is not None else config.get("default_segments", 16)
    final_connections = args.connections if args.connections is not None else config.get("default_connections", 16)
    final_segment_size = args.segment_size if args.segment_size is not None else config.get("default_segment_size", 4)
    final_concurrent_segments = args.concurrent_segments if args.concurrent_segments is not None else config.get("concurrent_segments", 10)

    # Resolve cookies source (flag > config). Premium quality needs cookies.
    final_cookies_browser = args.cookies_from_browser if args.cookies_from_browser else config.get("default_cookies_browser")
    final_cookies_file = args.cookies_file if args.cookies_file else config.get("default_cookies_file")
    final_js_runtime = args.js_runtime if args.js_runtime else config.get("default_js_runtime", "deno")
    if args.quality == "premium" and not (final_cookies_browser or final_cookies_file):
        print("[WARNING] 'premium' quality needs cookies from a logged-in YouTube Premium account.")
        print("          Pass --cookies-from-browser firefox (or --cookies-file cookies.txt).")
        print("          Without them, yt-dlp will fall back to standard 1080p.")

    # Prompt user for URL if not provided
    urls = args.link if args.link else []

    if not urls:
        url = get_link_from_user()
        if url:
            urls.append(url)
        else:
            print("[ERROR] No URL provided.")
            raise RuntimeError("No URL provided")
            # sys.exit(1)

    # Ensure folders exist
    os.makedirs(final_folder, exist_ok=True)
    os.makedirs(final_log_folder, exist_ok=True)

    # Setup logging
    log_file = loggingtool.setup_logging(final_log_folder)

    container = downloadtool.container_for_quality(args.quality)

    # One bad URL must not abandon the rest of the batch: record the failure,
    # keep going, and report everything that went wrong at the end.
    failures = []

    for index, url in enumerate(urls, start=1):
        # Determine next sequential filename (extension follows the container)
        output_filename = downloadtool.get_next_video_filename(final_folder, ext=container)
        print(f"[INFO] Downloading ({index}/{len(urls)}): {url}")
        try:
            downloadtool.download_video(
                url,
                args.quality,
                output_filename,
                final_segments,
                final_connections,
                final_segment_size,
                final_concurrent_segments,
                skip_conversion=args.do_not_convert,
                verbose=args.verbose,
                cookies_from_browser=final_cookies_browser,
                cookies_file=final_cookies_file,
                js_runtime=final_js_runtime
            )
        except KeyboardInterrupt:
            # Ctrl-C is a deliberate stop: abandon the whole batch.
            print("\n[ABORTED] Interrupted by user; skipping remaining downloads.")
            failures.append((url, "aborted by user"))
            break
        except Exception as exc:
            loggingtool.logging.error("Failed to download %s: %s", url, exc)
            print(f"[ERROR] Failed: {url} ({exc})")
            print("[INFO] Continuing with the next URL.")
            failures.append((url, str(exc)))

    return report_results(len(urls), failures, log_file)


def report_results(total: int, failures: list, log_file: str) -> int:
    """Print a batch summary and return the process exit code."""
    succeeded = total - len(failures)

    if not failures:
        print(f"\n[SUCCESS] All {total} download(s) completed.")
        return 0

    print(f"\n[SUMMARY] {succeeded}/{total} succeeded, {len(failures)} failed:")
    for url, reason in failures:
        print(f"  - {url}\n      {reason}")
    print(f"[INFO] Details in {log_file}")
    return 1
if __name__ == "__main__":
    sys.exit(main())