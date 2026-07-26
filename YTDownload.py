import argparse
import sys
import os
import shutil
import src.loggingtool as loggingtool
import src.downloadtool as downloadtool
import src.configmanager as configmanager
import subprocess

version: str = "1.0.2 master"
def configure_console_encoding():
    """
    Make stdout/stderr tolerate characters outside the console's code page.

    Windows consoles default to a legacy code page (cp1252), so printing a
    filename raises UnicodeEncodeError as soon as the title contains anything
    outside it. This is common rather than exotic: yt-dlp sanitises ASCII quotes
    in titles into fullwidth quotes (U+FF02), which cp1252 cannot encode. A
    download that already succeeded must not be reported as failed because its
    name could not be printed.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # Not a reconfigurable text stream (e.g. captured during tests).
            pass


def get_link_from_user() -> str:
    """Prompt the user to enter a YouTube URL if not provided as a flag."""
    return input("Enter YouTube video URL: ").strip()

# Every external binary the download path shells out to: the flag that makes it
# report its version, and the hint printed when it is missing. aria2c and yt-dlp
# used to fail deep inside the download with an opaque message instead of up front.
#
# The flag differs per tool and is not interchangeable: ffmpeg/ffprobe want the
# single-dash "-version", while "aria2c -version" is a parse error and
# "yt-dlp -version" is silently interpreted as --verbose.
REQUIRED_BINARIES = {
    "yt-dlp": ("--version", "pip install -U yt-dlp"),
    "ffmpeg": ("-version", "https://ffmpeg.org/download.html (or: winget install Gyan.FFmpeg)"),
    "ffprobe": ("-version", "ships with ffmpeg — install the full build, not ffmpeg.exe alone"),
    "aria2c": ("--version", "https://aria2.github.io (or: winget install aria2.aria2)"),
}


def check_binary(name: str) -> bool:
    """
    True if `name` is on PATH and runs. Checks the exit code as well as mere
    presence, so a broken or truncated install is not reported as working.
    """
    if shutil.which(name) is None:
        return False
    version_flag = REQUIRED_BINARIES.get(name, ("--version", ""))[0]
    try:
        result = subprocess.run(
            [name, version_flag],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def check_dependencies() -> list:
    """Return the names of required binaries that are missing or non-functional."""
    return [name for name in REQUIRED_BINARIES if not check_binary(name)]


def check_ffmpeg_installed() -> bool:
    """Check if ffmpeg is installed and available in PATH."""
    return check_binary("ffmpeg")

def main():
    configure_console_encoding()

    # Load config
    config = configmanager.load_config()

    # Check every external tool up front, not just ffmpeg
    missing = check_dependencies()
    if missing:
        print("[ERROR] Required tools are missing or not working:")
        for name in missing:
            print(f"  - {name}: {REQUIRED_BINARIES[name][1]}")
        raise RuntimeError(f"missing dependencies: {', '.join(missing)}")

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
    parser.add_argument("--sequential-names", action="store_true", help="Use the legacy videoNNN.ext naming instead of 'Channel - Title [id].ext'")
    parser.add_argument("--output-template", type=str, help="Custom yt-dlp output template (overrides the default naming)")
    parser.add_argument("--no-metadata", action="store_true", help="Do not embed title/channel metadata tags into the downloaded file")
    parser.add_argument("--archive", type=str, help="Path to the download archive file recording what has already been fetched (default: .download-archive.txt inside the download folder)")
    parser.add_argument("--no-archive", action="store_true", help="Ignore the download archive and re-download even if the video was fetched before")
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

    # Archive of what has already been fetched, so re-running a batch is
    # idempotent rather than producing duplicates under fresh sequence numbers.
    if args.no_archive:
        final_archive = None
        print("[INFO] Archive disabled — previously downloaded videos will be fetched again.")
    else:
        final_archive = args.archive or config.get("download_archive") \
            or downloadtool.default_archive_path(final_folder)

    # One bad URL must not abandon the rest of the batch: record the failure,
    # keep going, and report everything that went wrong at the end.
    failures = []
    skipped = []

    # Naming: descriptive by default, legacy sequential on request.
    if args.sequential_names:
        final_template = None
    else:
        final_template = os.path.join(
            final_folder,
            args.output_template or config.get("output_template",
                                               downloadtool.DEFAULT_OUTPUT_TEMPLATE)
        )

    for index, url in enumerate(urls, start=1):
        # Sequential naming needs the next free slot; template naming is resolved
        # by yt-dlp itself, so skip the directory scan entirely in that case.
        output_filename = (
            downloadtool.get_next_video_filename(final_folder, ext=container)
            if final_template is None
            else os.path.join(final_folder, f"video.{container}")
        )
        print(f"[INFO] Downloading ({index}/{len(urls)}): {url}")
        try:
            written = downloadtool.download_video(
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
                js_runtime=final_js_runtime,
                download_archive=final_archive,
                output_template=final_template,
                embed_metadata=not args.no_metadata
            )
            if written is None:
                skipped.append(url)
            else:
                print(f"[INFO] Saved: {os.path.basename(written)}")
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

    return report_results(len(urls), failures, log_file, skipped)


def report_results(total: int, failures: list, log_file: str, skipped: list = None) -> int:
    """Print a batch summary and return the process exit code."""
    skipped = skipped or []
    succeeded = total - len(failures) - len(skipped)

    if not failures:
        if skipped:
            print(f"\n[SUCCESS] {succeeded} downloaded, {len(skipped)} already in archive.")
        else:
            print(f"\n[SUCCESS] All {total} download(s) completed.")
        return 0

    print(f"\n[SUMMARY] {succeeded}/{total} succeeded, "
          f"{len(skipped)} skipped, {len(failures)} failed:")
    for url, reason in failures:
        print(f"  - {url}\n      {reason}")
    print(f"[INFO] Details in {log_file}")
    return 1
if __name__ == "__main__":
    sys.exit(main())