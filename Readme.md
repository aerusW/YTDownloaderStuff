# 🎬 YTDownloaderStuff

> A fast, **Windows-friendly YouTube downloader CLI** — multi-threaded aria2 downloads, clean progress bars, human-readable filenames, resumable batches, and browser-cookie auth that _actually works_ for Premium 1080p.

![Python](https://img.shields.io/badge/python-3.10%2B-blue?logo=python&logoColor=white)
![Platform](https://img.shields.io/badge/platform-Windows-0078D6?logo=windows&logoColor=white)
![Built with yt-dlp](https://img.shields.io/badge/built%20with-yt--dlp-red)
![aria2](https://img.shields.io/badge/downloader-aria2-orange)
![License: MIT](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-136%20passing-brightgreen)
![Stars](https://img.shields.io/github/stars/aerusW/YTDownloaderStuff?style=social)

```text
── 2/6 ──────────────────────────────────────────────────────
  https://youtu.be/KOpTWx1Eou4
  Fireship - The most interesting ＂hack＂ in his…[KOpT].mp4
   45% ━━━━━━━━━──────────  16MiB/s · ETA 8s
  ▸ merging video and audio
  ✓ saved · 15.9 MB
──────────────────────────────────────────────────────────────
✓ 5 downloaded · 1 skipped
```

## ✨ Highlights

* ⚡ **Multi-threaded downloads** via **aria2** — configurable segments and connections for full-bandwidth speed
* 📊 Clean, resizable **tqdm progress bars** for both download and audio conversion
* 🏷️ **Human-readable filenames** — `Channel - Title [videoID].ext` — with title/channel/date embedded as metadata
* 🔁 **Resumable batches** — already-fetched videos are skipped, so re-running never duplicates; one failure never aborts the rest
* 🎚️ **Quality selection** — `720`, `1080`, `4k`, and **`premium`** (YouTube's enhanced-bitrate VP9 `616`, saved losslessly as MKV)
* 🍪 **Browser-cookie auth that works** — auto-selects your signed-in profile and unlocks Premium 1080p ([details](COOKIES.md))
* 🎵 Automatic **AAC audio conversion** and MP4 merging for maximum compatibility

## 📑 Contents

- [Requirements](#requirements) · [Installation](#installation) · [Configuration](#configuration)
- [Usage](#usage) · [Cookies & Premium auth](#how-browser-cookies-are-read) · [Terminal output](#terminal-output)
- [Testing](#testing) · [Contributing](#contributing) · [License](#license)

---

## Requirements

You must have the following installed:

* **Python 3.10+**
* **ffmpeg** + **ffprobe** (on PATH)
* **aria2** (for multi-threaded downloads)
* **[Deno](https://deno.com)** — default JS runtime for YouTube's "n-challenge" (or Node.js via `--js-runtime node`)

> All four external tools (`yt-dlp`, `ffmpeg`, `ffprobe`, `aria2c`) are checked at
> startup and, if missing, reported up front with an install hint.

---

## Installation

Clone or download this project, then install Python dependencies:

```bash
pip install -r requirements.txt
```

---

## Configuration

Config is looked up in this order, and the first file found wins:

1. `<project root>/.config/config.json` — the config shipped with the repo
2. `$XDG_CONFIG_HOME/ytdownload/config.json`
3. `~/.config/ytdownload/config.json`
4. `%APPDATA%/ytdownload/config.json` (Windows)

These are absolute locations, so the tool can be launched from any directory.

```json
{
    "default_download_folder": "~\\Nextcloud\\Videos",
    "default_log_folder": "~\\Nextcloud\\Videos\\.DownloadLogs",
    "default_segments": 16,
    "default_connections": 16,
    "default_segment_size": 4,
    "concurrent_segments": 10,
    "default_cookies_browser": "firefox"
}
```

> CLI flags override these settings.

* `default_download_folder` — point this at a folder your media server watches
  (e.g. a **Nextcloud** synced folder) to stream downloads straight from your PC.
* `default_cookies_browser` — browser to read cookies from; required for `premium`
  quality so YouTube serves the enhanced-bitrate stream to your Premium account.
* `download_archive` — relocate the record of already-fetched videos.
* `output_template` — override the default filename template.

---

## Usage

### Basic

```bash
python YTDownload.py --link <YouTube_URL>
```

### With optional arguments

```text
--link <YouTube_URL>             # YouTube video URL, repeatable (required if no interactive input)
--quality {720,1080,premium,4k}  # Video quality (default: 1080). 'premium' = enhanced 1080p VP9 (MKV), needs cookies
--cookies-from-browser <browser> # Browser to read cookies from (chrome, firefox, edge). Needed for 'premium'
--cookies-file <path>            # Netscape cookies.txt to authenticate with
--folder <output_folder>         # Output folder (overrides config.json)
--log-folder <log_folder>        # Folder for logs (overrides config.json)
--segments <n>                   # Number of aria2 segments (overrides config)
--connections <n>                # Connections per segment (overrides config)
--segment-size <MB>              # Segment size in MB (overrides config)
--concurrent-segments <n>        # Number of concurrent segments to download (overrides config)
--sequential-names               # Legacy videoNNN.ext naming instead of 'Channel - Title [id].ext'
--output-template <template>     # Custom yt-dlp output template
--no-metadata                    # Do not embed title/channel tags into the file
--archive <path>                 # Archive file of what has already been fetched
--no-archive                     # Ignore the archive and re-download regardless
--do-not-convert                 # Skip AAC audio conversion
--js-runtime <name>              # JS runtime for YouTube's n-challenge (default: deno)
--verbose                        # Raw yt-dlp/ffmpeg output for debugging
-h, --help                       # Show help message
```

### Filenames

By default files are named from the video's own metadata:

```text
HONEST GUIDE - The unbeliveable beer story continues [6HRLlSdTmGY].mp4
```

The video ID keeps names unique when a channel reposts a title and makes each
file traceable back to YouTube. Title and channel are length-capped so the path
stays inside Windows' 260-character limit. Channel and title are also embedded
as metadata tags, so the information survives a rename (disable with
`--no-metadata`). Pass `--sequential-names` for the old `video001.mp4` scheme.

### Re-running a batch

Every fetched video is recorded in `.download-archive.txt` inside the download
folder, so re-running the same links skips them instead of creating duplicates:

```bash
python YTDownload.py --link https://youtu.be/VIDEOID   # downloads
python YTDownload.py --link https://youtu.be/VIDEOID   # [SKIP] already downloaded
python YTDownload.py --link https://youtu.be/VIDEOID --no-archive  # forces a re-download
```

A failing URL no longer abandons the rest of the batch — the remaining links
still download and a summary lists what failed.

**Example:**

```bash
python YTDownload.py --link https://youtu.be/VIDEOID --quality 4k --segments 12 --connections 12
```

**Premium 1080p example** (enhanced VP9 bitrate → MKV, using Firefox cookies):

```bash
python YTDownload.py --link https://youtu.be/VIDEOID --quality premium --cookies-from-browser firefox
```

> Premium formats are only served to logged-in YouTube Premium accounts. Make sure
> you're signed in to YouTube in the chosen browser. Without valid cookies, yt-dlp
> falls back to standard 1080p.

### How browser cookies are read

`--cookies-from-browser` is handled before yt-dlp sees it, so the *signed-in*
profile is used rather than whichever profile happens to be marked default:

* **Firefox** — every profile is scanned and the one actually holding YouTube
  login cookies is selected automatically. Pin one with
  `--cookies-from-browser firefox:C:\path\to\profile` to override.
* **Chrome / Edge / Brave (Windows)** — **close the browser first** (it locks
  its cookie database while running). The tool then obtains the master key
  (v10/DPAPI, or v20 App-Bound via the browser's elevation service), decrypts the
  cookies, and hands yt-dlp a temporary `cookies.txt`.

> **Heads up:** current Chrome/Edge versions protect the App-Bound cookie key
> with *caller validation* — the elevation service will only decrypt it for the
> browser itself, so no external program (this tool, yt-dlp, or anything else in
> your user session) can read those cookies. When that happens the tool tells you
> and you should use **Firefox** (fully supported) or export a `cookies.txt` for
> `--cookies-file`.

**Export a reusable `cookies.txt`** (portable, no browser needed at download time):

```bash
python -m src.browsercookies firefox "C:\path\to\cookies.txt"
python YTDownload.py --link https://youtu.be/VIDEOID --quality premium --cookies-file "C:\path\to\cookies.txt"
```

📖 **Cookie problems?** See **[COOKIES.md](COOKIES.md)** — a full troubleshooting
guide (bot check, wrong profile, App-Bound Encryption, exporting from Chrome).

## Testing

Run tests from the project root directory:

```bash
python -m pytest -v
```


## Terminal output

Output is grouped into one block per video (see the sample at the top of this
README) and reflows to the terminal width, re-measured on every redraw so
resizing mid-download does not smear the progress bar.

Two environment variables control appearance:

| Variable | Effect |
|---|---|
| `NO_COLOR=1` | Disable colour (also off automatically when piped or redirected) |
| `YTDOWNLOAD_ASCII=1` | Use `-`, `+`, `...` instead of box-drawing and Unicode symbols, for legacy consoles that cannot render them |

## Requirements checked at startup

`yt-dlp`, `ffmpeg`, `ffprobe` and `aria2c` must all be on PATH. Missing tools are
reported up front with an install hint rather than failing mid-download.

## Notes

* Videos are saved in your configured folder (set `default_download_folder` to a Nextcloud/media-server folder to stream them from your PC)
* `premium` quality produces **`.mkv`** files (VP9/Opus, untouched); other qualities produce `.mp4`
* Without Premium cookies, `premium` falls back to standard 1080p VP9
* A URL containing `&list=...` downloads only that video, not the playlist
* If no `--link` is provided, you will be prompted to input a URL interactively
* Flags override the settings in `config.json`
* Exit code is `1` if any download in the batch failed, `0` otherwise


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

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

By contributing, you agree that your contributions will be licensed under the MIT license.

---

<sub>Built on <a href="https://github.com/yt-dlp/yt-dlp">yt-dlp</a>, <a href="https://aria2.github.io">aria2</a>, and <a href="https://ffmpeg.org">ffmpeg</a>. If this saved you time, a ⭐ helps others find it.</sub>