# YTDownloadStuff

A **Windows-friendly YouTube downloader** with:

* Sequential filenames (`video001.mp4`, `video002.mp4`, …)
* Multi-threaded downloads via **aria2** with configurable segments and connections
* Clean **tqdm** download progress bars
* AAC audio conversion for Windows compatibility
* Automatic merging to MP4
* Optional quality selection (`720p`, `1080p`, `4k`)

---

## Requirements

You must have the following installed:

* **Python 3.10+**
* **ffmpeg** (added to PATH)
* **aria2** (for multi-threaded downloads)
* Node.js (optional, for yt-dlp JS runtime, recommended)

---

## Installation

Clone or download this project, then install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Configuration

Create a `config.json` file in `~/.config/config.json` if not present:

```json
{
    "default_download_folder": "~\\videos",
    "default_log_folder": "~\\videos\\.DownloadLogs",
    "default_segments": 16,
    "default_connections": 16,
    "default_segment_size": 4,
    "concurrent_segments": 10
}
```

> CLI flags override these settings.

---

## Usage

### Basic

```bash
python YTDownload.py --link <YouTube_URL>
```

### With optional arguments

```text
--link <YouTube_URL>          # YouTube video URL (required if no interactive input)
--quality {720,1080,4k}       # Video quality (default: 1080)
--folder <output_folder>       # Output folder (overrides config.json)
--log-folder <log_folder>      # Folder for logs (overrides config.json)
--segments <n>                 # Number of aria2 segments (overrides config)
--connections <n>              # Connections per segment (overrides config)
--segment-size <MB>            # Segment size in MB (overrides config)
--concurrent-segments          # Number of concurrent segments to download (overrides config)
-h, --help                     # Show help message
```

**Example:**

```bash
python YTDownload.py --link https://youtu.be/VIDEOID --quality 4k --segments 12 --connections 12
```


## Features

* Fast **segmented downloads** using **aria2**
* Real-time **tqdm** progress bars for both download and AAC conversion
* Automatic sequential filenames (`video001.mp4`, `video002.mp4`, …)
* Safe **AAC audio conversion** for Windows
* Configurable **segments, connections, and segment size** for optimal download speed
* Automatic MP4 merging

## Notes

* Videos are **saved sequentially** in your configured folder by default (`~/Videos/DownloadedVideos`)
* If no `--link` is provided, you will be prompted to input a URL interactively
* Flags override the settings in `config.json`
