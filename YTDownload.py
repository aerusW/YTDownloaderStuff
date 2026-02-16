import argparse
import subprocess
import sys
import os

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
    The original file is replaced by the converted one.
    """
    abs_input = os.path.abspath(filename)
    temp_file = abs_input.replace(".mp4", "_aac.mp4")

    command = [
        "ffmpeg",
        "-y",  # overwrite output if exists
        "-i", abs_input,
        "-c:v", "copy",  # copy video stream
        "-c:a", "aac",   # convert audio to AAC
        "-b:a", "192k",  # audio bitrate
        temp_file
    ]

    try:
        subprocess.run(command, check=True)
        os.remove(abs_input)
        os.rename(temp_file, abs_input)
        print(f"[SUCCESS] Audio converted to AAC: {abs_input}")
    except subprocess.CalledProcessError:
        print("[ERROR] FFmpeg conversion failed.")
        sys.exit(1)

def download_video(url: str, quality: str, output_filename: str):
    """
    Download a YouTube video with yt-dlp using aria2 for multi-threaded download.
    Merges video and audio automatically and converts audio to AAC afterwards.
    """
    format_string = build_format_string(quality)

    command = [
        "yt-dlp",
        "-f", format_string,
        "--cookies-from-browser", "firefox",  # use cookies from Firefox for authenticated downloads
        "--js-runtimes", "node",  # use Node.js for JavaScript execution (better performance)
        "--remote-components", "ejs:github",  # use EJS remote component for better performance
        "--merge-output-format", "mp4",  # merged output format
        "--external-downloader", "aria2c",  # use aria2 for speed
        "--external-downloader-args",
        "aria2c:-x 8 -s 8 -k 1M --file-allocation=none",
        "-o", output_filename,  # output filename
        url
    ]

    try:
        subprocess.run(command, check=True)
        print(f"[SUCCESS] Download finished: {output_filename}")
    except subprocess.CalledProcessError:
        print("[ERROR] Download failed.")
        sys.exit(1)

    # Convert audio to AAC for Windows compatibility
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
