# Cookies & authentication

Some downloads need you to be signed in to YouTube:

* **`premium` quality** (format 616, enhanced-bitrate 1080p VP9) is only served to
  logged-in YouTube Premium accounts.
* YouTube's **bot check** ("Sign in to confirm you're not a bot") is satisfied by
  a logged-in session.

You supply that session one of two ways:

| Flag | What it does |
|---|---|
| `--cookies-from-browser <browser>` | Reads cookies live from your browser |
| `--cookies-file <path>` | Reads a Netscape `cookies.txt` you exported once |

`--cookies-from-browser` is handled *before* yt-dlp sees it: the **signed-in
profile** is auto-selected, and on Windows Chrome/Edge/Brave the tool decrypts
the cookies itself. See [How browser cookies are read](Readme.md#how-browser-cookies-are-read).

---

## TL;DR by browser

* **Firefox — just works.** Stay signed in to YouTube. `--cookies-from-browser firefox`.
* **Chrome / Edge / Brave — often *cannot* be read.** Current versions lock the
  cookies behind App-Bound Encryption with caller validation (see below). If you
  hit that, use Firefox or a `cookies.txt`.

---

## Export a reusable `cookies.txt`

A `cookies.txt` is portable, works with `--cookies-file`, and doesn't need the
browser open (or even installed) at download time.

```bash
python -m src.browsercookies firefox "C:\path\to\cookies.txt"
```

Then:

```bash
python YTDownload.py --link https://youtu.be/VIDEOID --quality premium --cookies-file "C:\path\to\cookies.txt"
```

* Works for **Firefox** (cookies are not encrypted).
* For **Chrome/Edge** the same export command will report the App-Bound error —
  those cookies can't be exported by an external program. Use a browser
  extension instead (see the Chrome section below).
* Optionally pin a profile: `python -m src.browsercookies firefox:"C:\...\Profiles\xxxx.dev" cookies.txt`.

Re-export whenever the cookies get stale (you get logged out or the bot check
returns).

---

## Troubleshooting

### "Sign in to confirm you're not a bot", or `premium` quietly downloads as `.mp4`

The cookies aren't authenticating. Checklist:

1. **Are you actually signed in** to YouTube in that browser?
2. **Firefox with several profiles?** The signed-in one is auto-selected, but if
   detection is off, pin it:
   `--cookies-from-browser firefox:"C:\Users\<you>\AppData\Roaming\Mozilla\Firefox\Profiles\<profile>"`.
   List profiles with the folder `…\Mozilla\Firefox\Profiles`.
3. **Confirm it worked:** a successful premium download produces an `.mkv`; probe
   it with `ffprobe -show_entries stream=codec_name <file>` and you should see
   `vp9`. An `.mp4`/`avc1` result means it fell back — cookies didn't take.

### `[WARNING] Could not read chrome cookies: … the browser is holding its cookie database open`

Chrome/Edge lock the cookie database while running. **Close the browser
completely** (check the system tray — background apps keep it alive) and retry.

### `… App-Bound Encryption with caller validation … (0x8004A007)` or `(0x80004002)`

This is the hard wall. Since Chrome 127+, the cookie key is protected by
**App-Bound Encryption**, and current builds add **caller validation**: the
browser's elevation service only decrypts the key for the browser *itself*. No
external program — this tool, yt-dlp, or anything else running as you — can read
those cookies. It cannot be bypassed without running from the browser's install
directory, injecting into it, or running as SYSTEM, none of which this tool does.

**Fixes, in order of preference:**

1. **Use Firefox.** Sign in to YouTube in Firefox and use
   `--cookies-from-browser firefox`. Fully supported.
2. **Export a `cookies.txt` from Chrome with a browser extension**, then use
   `--cookies-file`:
   * Install a "cookies.txt" exporter (e.g. *Get cookies.txt LOCALLY*).
   * Open `https://www.youtube.com` while signed in.
   * Export, save the file, and pass it with `--cookies-file "C:\path\cookies.txt"`.
   * The extension runs *inside* the browser, so it isn't blocked by App-Bound
     Encryption.

### It worked yesterday, fails today

Cookies expire and YouTube rotates the bot-check periodically. Re-open the
browser (or re-export the `cookies.txt`) so a fresh session is picked up.

---

## Why Chrome is harder than Firefox

Firefox stores cookies in a plain SQLite database your own programs can read.
Chrome/Edge encrypt them with a key that, on current versions, only the browser
is allowed to unwrap — a deliberate anti-theft measure. That's why the reliable
paths for this tool are **Firefox** or an **in-browser `cookies.txt` export**.
