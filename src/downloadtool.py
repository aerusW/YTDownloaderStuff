import os
import sys
import re
import glob
import tempfile
import subprocess
from tqdm import tqdm
import src.loggingtool as loggingtool
import shutil


def build_format_string(quality: str) -> str: # Builds the yt-dlp format string based on the desired quality.
    # For 720/1080/4k this grabs the AVC/AAC version directly from YouTube (MP4-friendly).
    # For "premium" it targets format 616 — YouTube's enhanced-bitrate 1080p VP9 stream,
    # only served to logged-in Premium accounts (requires cookies).
    if quality == "premium":
        # The fallback chain is spelled out so it cannot silently drift from the
        # documented intent. The previous "616+bestaudio/bestvideo[height<=1080]
        # +bestaudio/b" left tier 2 uncodeced, so without cookies it quietly
        # returned AV1 while the docs promised VP9.
        #
        # vcodec~='^vp0?9' matches both spellings YouTube uses: bare "vp9" and
        # the ISO-style "vp09.00.40.08".
        return (
            "616+bestaudio"                                  # enhanced 1080p VP9 (Premium + cookies)
            "/bv*[height<=1080][vcodec~='^vp0?9']+bestaudio"  # standard 1080p VP9
            "/bv*[height<=1080]+bestaudio"                    # any 1080p (AV1/AVC)
            "/b"                                              # whatever is left
        )
    elif quality == "4k":
        return "bv*[height<=2160][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/b"
    elif quality == "720":
        return "bv*[height<=720][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/b"
    else:
        return "bv*[height<=1080][vcodec^=avc1]+ba[ext=m4a]/b[ext=mp4]/b"


def container_for_quality(quality: str) -> str:
    """
    Premium (VP9) is kept losslessly in MKV; everything else stays MP4.
    """
    return "mkv" if quality == "premium" else "mp4"


def get_next_video_filename(folder: str, ext: str = "mp4") -> str:
    """
    Find the next available sequential filename like video001.mp4 in the folder.
    The extension follows the chosen container (mp4 or mkv).

    A slot counts as taken if video### exists under *any* extension. Checking
    only the target extension used to hand out video001.mp4 in a folder that
    already held video001.mkv, producing pairs that are indistinguishable by
    name and hiding which run produced which file.
    """
    i = 1
    while True:
        stem = os.path.join(folder, f"video{i:03}")
        if not glob.glob(glob.escape(stem) + ".*"):
            return f"{stem}.{ext}"
        i += 1


def probe_audio_codec(path: str) -> str:
    """
    Audio codec of an existing file, via ffprobe; "unknown" if it cannot be read.

    Probing the finished file replaces a second yt-dlp metadata pass over the
    network, and is more accurate: it reports what was actually muxed rather
    than what the format selector was expected to pick.
    """
    try:
        output = subprocess.check_output(
            [
                "ffprobe",
                "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_name",
                "-of", "default=noprint_wrappers=1:nokey=1",
                path,
            ],
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError):
        return "unknown"
    return output.decode(errors="replace").strip() or "unknown"


def aac_temp_path(path: str) -> str:
    """
    Scratch path ffmpeg writes the AAC remux to, before it replaces the original.

    Uses splitext rather than str.replace(".mp4", ...): replace() rewrites every
    occurrence, so a folder such as D:\\clips.mp4.old\\ would have its directory
    name mangled and the rename would land somewhere that does not exist.
    """
    stem, suffix = os.path.splitext(path)
    return f"{stem}_aac{suffix}"


def convert_audio_to_aac(filename: str, verbose: bool = False):
    """
    Convert video audio to AAC using ffmpeg.
    Video stream is copied without re-encoding to preserve quality.
    Displays a tqdm progress bar.
    """
    abs_input = os.path.abspath(filename)
    temp_file = aac_temp_path(abs_input)

    # Get total duration using ffprobe
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        abs_input
    ]

    try:
        total_duration = float(subprocess.check_output(probe_cmd).decode().strip())
    except Exception:
        print("[ERROR] Could not determine video duration.")
        # sys.exit(1)
        raise RuntimeError("Failed to get video duration")

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i", abs_input,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-progress", "pipe:1",
        "-nostats",
        temp_file
    ]
    if verbose:
        print(f"[VERBOSE] Executing ffmpeg: {' '.join(ffmpeg_cmd)}\n")

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    progress_bar = tqdm(total=total_duration, desc="Converting", unit="s", ncols=100)
    time_pattern = re.compile(r"out_time_ms=(\d+)")

    try: # Loop through ffmpeg output to update progress bar based on out_time_ms
        for line in process.stdout:
            match = time_pattern.search(line)
            if match:
                out_time_ms = int(match.group(1))
                current_time = out_time_ms / 1_000_000
                progress_bar.n = min(current_time, total_duration)
                progress_bar.refresh()

        process.wait()
        progress_bar.n = total_duration
        progress_bar.refresh()
        progress_bar.close()

        if process.returncode != 0:
            print("\n[ERROR] FFmpeg conversion failed.")
            # sys.exit(1)
            raise RuntimeError("FFmpeg conversion failed")

        os.remove(abs_input)
        os.rename(temp_file, abs_input)
        print("[SUCCESS] Audio converted to AAC.")

    except KeyboardInterrupt:
        process.kill()
        progress_bar.close()
        print("\n[ABORTED]")
        # sys.exit(1)
        raise RuntimeError("Conversion aborted by user")

def read_reported_path(report_file: str) -> str:
    """
    Read the path yt-dlp reported via --print-to-file after_move:%(filepath)s.

    Returns the last non-empty line, or "" if yt-dlp wrote nothing — which
    happens when no file was produced (e.g. the download was skipped).
    """
    try:
        with open(report_file, "r", encoding="utf-8") as f:
            lines = [line.strip() for line in f if line.strip()]
    except OSError:
        return ""
    return lines[-1] if lines else ""


def download_video(url: str, quality: str, output_filename: str, segments: int, max_connections: int, segment_size: int, concurrent_segments: int, skip_conversion: bool = False, verbose: bool = False, cookies_from_browser: str = None, cookies_file: str = None, js_runtime: str = "deno", remote_components: str = "ejs:github"):
    """
    Download a YouTube video with yt-dlp using aria2.
    Converts audio to AAC after download (MP4 path only).

    cookies_from_browser: browser spec (e.g. "chrome" or "firefox:PROFILE_PATH")
        whose cookies yt-dlp should use. Required to unlock Premium formats such as
        616 (1080p enhanced VP9) and to satisfy YouTube's bot check.
    cookies_file:  path to a Netscape cookies.txt (alternative to reading a live
        browser; survives uninstalling the browser).
    js_runtime:    JavaScript runtime used to solve YouTube's "n challenge"
        (default "deno" — required by current YouTube; "node" also possible).
    remote_components: yt-dlp EJS solver source (default "ejs:github"); needed so
        the challenge solver script stays up to date, else formats go missing.
    """
    full_output = []
    format_string = build_format_string(quality)
    container = container_for_quality(quality)

    base_name = os.path.splitext(output_filename)[0]

    aria_progress_pattern = re.compile(
        r"\[(?:#\w+\s+)?(\d+\.?\d*\w*)\/(\d+\.?\d*\w*)\((\d+)%\)\s+CN:\d+\s+DL:(\d+\.?\d*\w*)\s+ETA:(\d+\w*)\]"
    )

    # Ask yt-dlp to report the path it actually wrote, rather than assuming it
    # matches output_filename. The format strings end in "/b", and a single
    # pre-muxed fallback stream skips the merger and keeps its own extension,
    # so the guessed name can point at a file that was never created.
    #
    # --print-to-file rather than --print: --print implies --quiet, which would
    # suppress the progress output this function parses. --print-to-file does not.
    report_dir = tempfile.mkdtemp(prefix="ytdownload-")
    report_file = os.path.join(report_dir, "filepath.txt")

    command = [ # Construct the yt-dlp command with aria2 and progress parsing
        "yt-dlp",
        "--js-runtimes", js_runtime,
        "--remote-components", remote_components,
        "-f", format_string,
        "--newline",
        "--no-color",
        # A shared URL often carries &list=...; without this yt-dlp pulls the
        # whole playlist into the single filename slot reserved for one video.
        "--no-playlist",
        "--merge-output-format", container,
        "--print-to-file", "after_move:%(filepath)s", report_file,
        "--external-downloader", "aria2c",
        "--external-downloader-args", f"aria2c:-x {max_connections} -s {segments} -k {segment_size}M --file-allocation=none --summary-interval=1 --console-log-level=warn --disable-ipv6=true", # --disable-ipv6: Google's CDN often resolves to IPv6; forcing IPv4 avoids "unreachable network" failures on IPv4-only connections
        "--concurrent-fragments", f"{concurrent_segments}",
        "-o", f"{base_name}.%(ext)s",
        url
    ]
    if cookies_from_browser:
        command[1:1] = ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        command[1:1] = ["--cookies", cookies_file]

    if verbose:
        print(f"\n[VERBOSE] aria2 settings: {segments} segments, {segment_size}MB chunks, {max_connections} connections, {concurrent_segments} concurrent")
        print(f"[VERBOSE] Executing yt-dlp: {' '.join(command)}\n")
        
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, # Safely handles the output buffer
        universal_newlines=True,
        errors="replace"          
    )

    progress_bar = None

    try:
        # Loop through the output stream to catch errors and print status
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            
            full_output.append(line)

            if verbose:
                # In verbose mode, just dump the raw terminal output
                print(f"[DEBUG] {line}")
            else:
                # In non-verbose mode, manage the clean UI and progress bar
                if "[download] Destination:" in line:
                    if progress_bar:
                        progress_bar.n = 100
                        progress_bar.refresh()
                        progress_bar.close()
                        progress_bar = None
                    
                    filename = line.split("\\")[-1] if "\\" in line else line.split("/")[-1]
                    print(f"[INFO] Downloading stream: {filename}")

                elif "[Merger] Merging formats" in line:
                    if progress_bar:
                        progress_bar.n = 100
                        progress_bar.refresh()
                        progress_bar.close()
                        progress_bar = None
                    print("[INFO] Merging video and audio (this takes a few seconds)...")

                else:
                    match = aria_progress_pattern.search(line)
                    if match:
                        downloaded_str, total_str, percent, speed_str, eta_str = match.groups()
                        percent = int(percent)

                        if progress_bar is None:
                            progress_bar = tqdm(total=100, desc="Downloading", ncols=100)

                        progress_bar.n = percent
                        progress_bar.set_postfix({"Speed": speed_str, "ETA": eta_str})
                        progress_bar.refresh()

        process.wait()

        # Clean up the progress bar if the process ends unexpectedly
        if progress_bar:
            progress_bar.n = 100
            progress_bar.refresh()
            progress_bar.close()

        if process.returncode != 0:
            error_message = "\n".join(full_output)
            loggingtool.logging.error("Download failed:\n%s", error_message)
            print("\n[ERROR] Download failed. See log for details.")
            # sys.exit(1)
            raise RuntimeError("Download failed")

        print("[SUCCESS] Download finished.")

        # Trust yt-dlp's own report over the predicted name; fall back to the
        # prediction only if nothing was reported.
        final_path = read_reported_path(report_file) or output_filename
        if verbose:
            print(f"[VERBOSE] yt-dlp wrote: {final_path}")
        if not os.path.exists(final_path):
            loggingtool.logging.error("Expected output missing after download: %s", final_path)
            raise RuntimeError(f"Download reported success but {final_path} is missing")

        audio_codec = probe_audio_codec(final_path)
        if verbose:
            print(f"[VERBOSE] Detected audio codec: {audio_codec}")
        is_aac = "aac" in audio_codec.lower() or "mp4a" in audio_codec.lower()

        # MKV (Premium VP9/AV1 + Opus) is kept as-is — re-muxing to AAC/MP4 would
        # break the video stream and throw away the enhanced quality.
        if os.path.splitext(final_path)[1].lower() == ".mkv":
            if verbose:
                print("[VERBOSE] MKV output — leaving video/Opus audio untouched.")
        elif not skip_conversion and not is_aac:
            convert_audio_to_aac(final_path, verbose=verbose)
        elif is_aac:
            if verbose:
                print("[VERBOSE] Detected audio is already AAC. Skipping conversion.")

        return final_path

    except KeyboardInterrupt:
        process.kill()
        if progress_bar:
            progress_bar.close()
        print("\n[ABORTED]")
        # sys.exit(1)
        raise RuntimeError("Download aborted by user")
    finally:
        shutil.rmtree(report_dir, ignore_errors=True)