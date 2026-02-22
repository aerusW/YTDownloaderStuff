import os
import sys
import re
import subprocess
from tqdm import tqdm
from yt_dlp import YoutubeDL
import loggingtool
import shutil


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
    abs_input = os.path.abspath(filename)
    temp_file = abs_input.replace(".mp4", "_aac.mp4")

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
        sys.exit(1)

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

    process = subprocess.Popen(
        ffmpeg_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )

    progress_bar = tqdm(total=total_duration, desc="Converting", unit="s", ncols=100)
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

def get_best_encoder():
    """
    Detects the best available hardware encoder.
    Returns the ffmpeg string for yt-dlp postprocessor-args.
    """
    # 1. Check for Nvidia
    if shutil.which("nvidia-smi"):
        # p4 is a good balance for speed/quality on Maxwell or newer
        return "ffmpeg:-c:v h264_nvenc -preset p4 -tune hq"
    
    # 2. Check for Intel/AMD via VA-API (Linux specific)
    # Most Linux distros use VA-API for non-Nvidia hardware acceleration
    if shutil.which("vainfo"):
        return "ffmpeg:-c:v h264_vaapi -vaapi_device /dev/dri/renderD128"
    
    # 3. Check for Windows AMD (AMF)
    if shutil.which("dxdiag"): # Very basic check for Windows env
         return "ffmpeg:-c:v h264_amf"

    # 4. Fallback to CPU (Standard)
    return "ffmpeg:-c:v libx264 -preset superfast"

def download_video(url: str, quality: str, output_filename: str, segments: int, max_connections: int, segment_size: int, concurrent_segments: int):
    """
    Download a YouTube video with yt-dlp using aria2 and a real tqdm progress bar.
    Converts audio to AAC after download.
    """
    full_output = []
    format_string = build_format_string(quality)

    aria_progress_pattern = re.compile(
        r"\[(?:#\w+\s+)?(\d+\.?\d*\w*)\/(\d+\.?\d*\w*)\((\d+)%\)\s+CN:\d+\s+DL:(\d+\.?\d*\w*)\s+ETA:(\d+\w*)\]"
    )

    base_name = os.path.splitext(output_filename)[0]

    # Detect GPU capabilities
    gpu_args = get_best_encoder()
    base_name = os.path.splitext(output_filename)[0]
    command = [
            "yt-dlp",
            "-f", format_string,
            "--newline",
            "--no-color",
            "--merge-output-format", "mp4",
            "--external-downloader", "aria2c",
            "--external-downloader-args", f"aria2c:-x {max_connections} -s {segments} -k {segment_size}M --file-allocation=none --summary-interval=1 --console-log-level=warn",
            "--concurrent-fragments", f"{concurrent_segments}",
            "--postprocessor-args", gpu_args,
            "-o", f"{base_name}.%(ext)s", 
            url
        ]
    print(f"segments: {segments}, connections: {max_connections}, segment size: {segment_size}MB, concurrent segments: {concurrent_segments}") # debug print for aria2 settings
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True
    )

    progress_bar = None

    try:
        for line in process.stdout:
            line = line.strip()
            if line:
                full_output.append(line)

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
        stderr_output = process.stderr.read()

        if progress_bar:
            progress_bar.n = 100
            progress_bar.refresh()
            progress_bar.close()

        if process.returncode != 0:
            error_message = "\n".join(full_output) + "\n" + stderr_output
            loggingtool.logging.error("Download failed:\n%s", error_message)
            print("\n[ERROR] Download failed. See log for details.")
            sys.exit(1)

        print("[SUCCESS] Download finished.")
        if not skip_conversion:
            convert_audio_to_aac(output_filename)

    except KeyboardInterrupt:
        process.kill()
        print("\n[ABORTED]")
        sys.exit(1)
