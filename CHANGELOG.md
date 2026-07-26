# Changelog

## 1.1.0

### Added

* Descriptive filenames — `Channel - Title [videoID].ext` — now the default.
  `--sequential-names` restores the previous `video001.mp4` scheme.
* Title, channel and upload date are embedded as metadata tags, so the
  information survives a rename. Disable with `--no-metadata`.
* A download archive (`.download-archive.txt` in the download folder) records
  what has been fetched, so re-running a batch skips instead of duplicating.
  `--no-archive` forces a re-download; `--archive` relocates the file.
* `--output-template` for a custom yt-dlp naming template.
* Output is grouped into one block per video and reflows to the terminal width.
  `NO_COLOR=1` disables colour, `YTDOWNLOAD_ASCII=1` swaps box-drawing and
  symbols for ASCII on consoles that cannot render them.
* Batch summary reporting, and a non-zero exit code when any download failed.

### Fixed

* **Config was only loaded when running from the project root.** The Windows
  branch looked for `src/.config/config.json`, which never exists, and the
  fallback resolved a relative path against the working directory. Launched
  from anywhere else, every setting silently reverted to a built-in default.
* **One failing URL abandoned the rest of the batch.** Failures are now
  collected and the remaining links still download.
* **Sequential filenames collided across containers.** A folder holding
  `video001.mkv` was handed `video001.mp4`, producing pairs that could not be
  told apart by name.
* **`premium` quality silently returned AV1 instead of VP9.** The fallback tier
  placed no codec constraint, so without Premium cookies it never matched the
  documented intent.
* **The output path was predicted rather than observed.** A single pre-muxed
  fallback stream skips the merger and keeps its own extension, so the AAC
  conversion ran against a file that was never created.
* **A URL containing `&list=` downloaded the entire playlist** into the single
  filename slot reserved for one video.
* **Only ffmpeg was checked at startup.** `ffprobe`, `aria2c` and `yt-dlp` are
  equally required and now fail fast with an install hint; exit codes are
  checked, so a present-but-broken binary no longer passes.
* **Titles containing characters outside the console code page failed the
  download.** yt-dlp rewrites ASCII quotes as fullwidth quotes (U+FF02), which
  a cp1252 Windows console cannot encode — printing the name of a download that
  had already succeeded raised `UnicodeEncodeError` and it was reported failed.
* **Progress bars did not adapt to terminal width.** A hardcoded `ncols=100`
  wrote lines wider than a narrower window; they wrapped and smeared down the
  screen, and resizing mid-download had no effect.
* **Layout miscounted double-width characters.** Fullwidth glyphs occupy two
  columns but count as one character, so lines measured as flush overflowed.
* `str.replace(".mp4", ...)` when building the AAC scratch path rewrote every
  occurrence, mangling any download folder whose name contained `.mp4`.
* `.gitignore` was UTF-16 encoded and could not be parsed by git.

### Changed

* Metadata is no longer fetched through the `yt-dlp` Python API. The audio codec
  is read by probing the finished file, removing a second network extraction per
  video (and a second solve of YouTube's n-challenge) and the requirement that
  the pip package and the CLI binary be installed and version-matched.
* Config is looked up at absolute locations: project root, then
  `$XDG_CONFIG_HOME`, `~/.config`, and `%APPDATA%`.

### Known issues

* `--cookies-from-browser` cannot read Chrome or Edge cookies on Windows due to
  App-Bound Encryption. Use Firefox, or `--cookies-file` with a Netscape
  `cookies.txt`. Without cookies, `premium` falls back to standard 1080p VP9.
* `--quality 4k` requires an AVC stream (`vcodec^=avc1`). YouTube serves 2160p
  as VP9/AV1 only, so on a genuinely 4K video this caps at 1080p.

## 1.0.2

* Initial versioned release: sequential filenames, aria2 segmented downloads,
  tqdm progress bars, AAC conversion, and `premium` (VP9/MKV) quality.
