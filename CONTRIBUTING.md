# Contributing to YTDownloaderStuff

Thanks for taking the time to contribute! 🎉 Bug reports, feature ideas,
documentation fixes, and pull requests are all welcome.

This document explains how to set up a development environment and get a change
merged. By participating you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).

---

## Ways to contribute

- 🐛 **Report a bug** — open a [bug report](../../issues/new?template=bug_report.yml).
- 💡 **Request a feature** — open a [feature request](../../issues/new?template=feature_request.yml).
- 📖 **Improve the docs** — typos, clarifications, and examples are always useful.
- 🔧 **Send a pull request** — see the workflow below.

For cookie/authentication problems, please read
[COOKIES.md](COOKIES.md) first — most are answered there.

---

## Development setup

**Prerequisites** (must be on your `PATH`):

| Tool | Purpose | Install |
|---|---|---|
| Python 3.10+ | runs the tool | [python.org](https://www.python.org/downloads/) |
| ffmpeg + ffprobe | merging & audio conversion | `winget install Gyan.FFmpeg` |
| aria2 | multi-threaded downloads | `winget install aria2.aria2` |
| Deno | YouTube's JS "n-challenge" | [deno.com](https://deno.com) |

**Clone and install Python dependencies:**

```bash
git clone https://github.com/aerusW/YTDownloaderStuff.git
cd YTDownloaderStuff
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

**Run the tool:**

```bash
python YTDownload.py --link https://youtu.be/VIDEOID
```

---

## Running the tests

Tests use `pytest` and live in `tests/`. Run them from the project root:

```bash
python -m pytest -q
```

A `tests/conftest.py` puts the project root on `sys.path`, so plain `pytest`
works from any directory too. All tests must pass before a PR is merged.

---

## Project layout

```
YTDownload.py          # CLI entry point (argument parsing, batch orchestration)
src/
  browsercookies.py    # browser-cookie resolution, decryption and export
  configmanager.py     # config file discovery and loading
  console.py           # terminal presentation (progress bars, colour, layout)
  downloadtool.py      # the yt-dlp + aria2 download pipeline
  loggingtool.py       # logging setup
tests/                 # pytest suite (one test_*.py per module)
```

---

## Pull request workflow

1. **Fork** the repository and create a branch off `master`:
   ```bash
   git checkout -b feat/short-description
   ```
2. **Make your change.** Keep commits focused; write a clear, imperative commit
   subject (e.g. `Fix cookie expiry unit on Firefox`).
3. **Add tests** for new behaviour and make sure the whole suite passes.
4. **Update the docs** (`Readme.md`, `COOKIES.md`, `CHANGELOG.md`) when your
   change is user-visible.
5. **Push** and open a pull request. Fill in the PR template and link any
   related issue.

### Code standards

- Match the style of the surrounding code — comment density, naming, and idiom.
- Add a docstring to new functions and classes; explain the *why*, not just the *what*.
- Prefer clear, small functions over cleverness.
- Don't introduce new third-party dependencies without discussing it first.

---

## Reporting security issues

Please **do not** open a public issue for security-sensitive problems. Email the
maintainer at francesco.serangeli@proton.me instead.
