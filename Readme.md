# YTDownload

A Windows-friendly YouTube downloader with:

* Sequential filenames (`video001.mp4`, `video002.mp4`, ...)
* Multi-threaded downloads via **aria2**
* Clean **tqdm** download progress bars
* AAC audio conversion for Windows compatibility
* Automatic merging to MP4

---

## Requirements

You must have the following installed:

* Python 3.10+
* **ffmpeg** (added to PATH)
* **aria2**
* Node.js (optional, recommended for yt-dlp JS runtime)

---

## Installation

Clone or download this project, then install the Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Usage

Basic usage:

```bash
python YTDownload.py --link <YouTube_URL>
```

Optional arguments:

```text
--quality {720,1080,4k}    # Download quality
--folder <output_folder>    # Output folder (default: ~/Videos/DownloadedVideos)
--log-folder <log_folder>    # Folder for logs (default: ~/Videos/DownloadedVideos)
-h, --help                  # Show help message
```

**Example:**

```bash
python YTDownload.py --link https://youtu.be/VIDEOID --quality 4k
```

By default, videos are saved in:

```
~/Videos/DownloadedVideos
```

With automatic sequential naming.

---

## Features

* Fast segmented downloads using **aria2**
* Real-time progress bars for download and conversion
* Clean terminal output
* Safe AAC audio conversion for Windows
* Windows-optimized workflow
