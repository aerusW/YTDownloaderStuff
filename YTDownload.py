import argparse
import subprocess
import sys
import os
from tqdm import tqdm # for progress bar 
from yt_dlp import YoutubeDL # for downloading YouTube videos
import re # for regex parsing of aria2 output

def get_link_from_user() -> str:
    """Prompt the user to enter a YouTube URL if not provided as a flag."""
    return input("Enter YouTube video URL: ").strip()

def build_format_string(quality: str) -> str:
    """
    Build yt-dlp format string:
    - Prefer H.264 video (Windows-friendly)
    - Merge with best audio
    - Default is 1080p if not specified
    """
    if quality == "4k":
        return "bv*[height<=2160][vcodec^=avc1]+ba/b"
    elif quality == "720":
        return "bv*[height<=720][vcodec^=avc1]+ba/b"
    else:  # 1080p default
        return "bv*[height<=1080][vcodec^=avc1]+ba/b"

def get_next_video_filename(folder: str) -> str:
    """
    Find the next available sequential filename like video001.mp4 in the folder.
    """
    i = 1
    while True:
        filename = os.path.join(folder, f"video{i:03}.mp4")
        if not os.path.exists(filename):
            return filename
        i += 1

def convert_audio_to_aac(filename: str):
    """
    Convert video audio to AAC using ffmpeg.
    Video stream is copied without re-encoding to preserve quality.
    Displays a tqdm progress bar.
    """
    import subprocess
    import re
    from tqdm import tqdm

    abs_input = os.path.abspath(filename)
    temp_file = abs_input.replace(".mp4", "_aac.mp4")

    # First get total duration using ffprobe
    probe_cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        abs_input
    ]

    try:
        total_duration = float(
            subprocess.check_output(probe_cmd).decode().strip()
        )
    except Exception:
        print("[ERROR] Could not determine video duration.")
        sys.exit(1)

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i", abs_input,
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-progress", "pipe:1",   # machine-readable progress
        "-nostats",
        temp_file
    ]

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    progress_bar = tqdm(
        total=total_duration,
        desc="Converting",
        unit="s",
        ncols=100
    )

    time_pattern = re.compile(r"out_time_ms=(\d+)")

    try:
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
            sys.exit(1)

        os.remove(abs_input)
        os.rename(temp_file, abs_input)
        print("[SUCCESS] Audio converted to AAC.")

    except KeyboardInterrupt:
        process.kill()
        progress_bar.close()
        print("\n[ABORTED]")
        sys.exit(1)


def download_video(url: str, quality: str, output_filename: str):
    """
    Download a YouTube video with yt-dlp using aria2 and a real tqdm progress bar.
    """

    format_string = build_format_string(quality)

    # Regex to parse aria2 progress line
    aria_progress_pattern = re.compile(
        r"\[(?:#\w+\s+)?(\d+\.?\d*\w*)\/(\d+\.?\d*\w*)\((\d+)%\)\s+CN:\d+\s+DL:(\d+\.?\d*\w*)\s+ETA:(\d+\w*)\]"
    )

    command = [
        "yt-dlp",
        "-f", format_string,
        "--newline",
        "--no-color",
        "--merge-output-format", "mp4",
        "--external-downloader", "aria2c",
        "--external-downloader-args",
        "aria2c:-x 8 -s 8 -k 1M --file-allocation=none --summary-interval=1 --console-log-level=warn",
        "-o", output_filename,
        url
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    progress_bar = None

    try:
        for line in process.stdout:
            line = line.strip()

            match = aria_progress_pattern.search(line)
            if match:
                downloaded_str, total_str, percent, speed_str, eta_str = match.groups()

                percent = int(percent)

                if progress_bar is None:
                    progress_bar = tqdm(
                        total=100,
                        desc="Downloading",
                        ncols=100
                    )

                progress_bar.n = percent
                progress_bar.set_postfix({
                    "Speed": speed_str,
                    "ETA": eta_str
                })
                progress_bar.refresh()

        process.wait()

        if progress_bar:
            progress_bar.n = 100
            progress_bar.refresh()
            progress_bar.close()

        if process.returncode != 0:
            print("\n[ERROR] Download failed.")
            sys.exit(1)

        print("[SUCCESS] Download finished.")

    except KeyboardInterrupt:
        process.kill()
        print("\n[ABORTED]")
        sys.exit(1)

    convert_audio_to_aac(output_filename)

def main():
    # Set default folder to Videos/DownloadedVideos in the user's home directory
    home = os.path.expanduser("~")
    default_folder = os.path.join(home, "Videos", "DownloadedVideos")
    os.makedirs(default_folder, exist_ok=True)

    parser = argparse.ArgumentParser(description="YouTube downloader with sequential filenames")
    parser.add_argument("--link", type=str, help="YouTube video URL")
    parser.add_argument(
        "--quality",
        choices=["720", "1080", "4k"],
        default="1080",
        help="Video quality (default: 1080p)"
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=default_folder,
        help=f"Output folder for downloaded videos (default: {default_folder})"
    )

    args = parser.parse_args()

    # Prompt user for URL if not provided
    url = args.link if args.link else get_link_from_user()
    if not url:
        print("[ERROR] No URL provided.")
        sys.exit(1)

    # Ensure the folder exists
    os.makedirs(args.folder, exist_ok=True)

    # Determine next sequential filename
    output_filename = get_next_video_filename(args.folder)

    download_video(url, args.quality, output_filename)

if __name__ == "__main__":
    main()
