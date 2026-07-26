# YTDownloadStuff

A **Windows-friendly YouTube downloader** with:

* Sequential filenames (`video001.mp4`, `video002.mp4`, …)
* Multi-threaded downloads via **aria2** with configurable segments and connections
* Clean **tqdm** download progress bars
* AAC audio conversion for Windows compatibility
* Automatic merging to MP4
* Optional quality selection (`720p`, `1080p`, `premium`, `4k`)
* **Premium 1080p** support (YouTube's enhanced-bitrate VP9 stream, format `616`) saved losslessly as MKV — requires cookies from a logged-in YouTube Premium account

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
    "default_download_folder": "~\\Nextcloud\\Videos",
    "default_log_folder": "~\\Nextcloud\\Videos\\.DownloadLogs",
    "default_segments": 16,
    "default_connections": 16,
    "default_segment_size": 4,
    "concurrent_segments": 10,
    "default_cookies_browser": "chrome"
}
```

> CLI flags override these settings.

* `default_download_folder` — point this at a folder your media server watches
  (e.g. a **Nextcloud** synced folder) to stream downloads straight from your PC.
* `default_cookies_browser` — browser to read cookies from; required for `premium`
  quality so YouTube serves the enhanced-bitrate stream to your Premium account.

---

## Usage

### Basic

```bash
python YTDownload.py --link <YouTube_URL>
```

### With optional arguments

```text
--link <YouTube_URL>              # YouTube video URL (required if no interactive input)
--quality {720,1080,premium,4k}  # Video quality (default: 1080). 'premium' = enhanced 1080p VP9 (MKV), needs cookies
--cookies-from-browser <browser> # Browser to read cookies from (chrome, firefox, edge). Needed for 'premium'
--folder <output_folder>          # Output folder (overrides config.json)
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

**Premium 1080p example** (enhanced VP9 bitrate → MKV, using Chrome cookies):

```bash
python YTDownload.py --link https://youtu.be/VIDEOID --quality premium --cookies-from-browser chrome
```

> Premium formats are only served to logged-in YouTube Premium accounts. Make sure
> you're signed in to YouTube in the chosen browser. Without valid cookies, yt-dlp
> falls back to standard 1080p.

## Testing

Run tests from the project root directory:

```bash
python -m pytest -v
```


## Features

* Fast **segmented downloads** using **aria2**
* Real-time **tqdm** progress bars for both download and AAC conversion
* Automatic sequential filenames (`video001.mp4`, `video002.mp4`, …)
* Safe **AAC audio conversion** for Windows
* Configurable **segments, connections, and segment size** for optimal download speed
* Automatic MP4 merging

## Notes

* Videos are **saved sequentially** in your configured folder (set `default_download_folder` to a Nextcloud/media-server folder to stream them from your PC)
* `premium` quality produces **`.mkv`** files (VP9/Opus, untouched); other qualities produce `.mp4`
* If no `--link` is provided, you will be prompted to input a URL interactively
* Flags override the settings in `config.json`


## Contributing

Contributions are welcome! Please follow these guidelines:

### Getting Started

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Make your changes and commit them (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

### Code Standards

* Add tests for new functionality
* Ensure all tests pass before submitting a PR
* Include docstrings for functions and classes

### Reporting Issues

* Check existing issues before opening a new one
* Provide clear descriptions and steps to reproduce
* Include your Python version and OS

### License

## License

This project is licensed under the GPL V3 License. See the [LICENSE](LICENSE) file for details.

By contributing, you agree that your contributions will be licensed under the GPL V3 license.