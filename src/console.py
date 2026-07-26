"""
Terminal presentation helpers.

Everything here re-reads the terminal width at call time rather than caching it,
so output reflows when the window is resized mid-download instead of smearing
across wrapped lines.
"""

import os
import sys
import shutil
import unicodedata

from tqdm import tqdm

# Width used when the terminal size cannot be determined (piped output, CI).
FALLBACK_WIDTH = 80

# Narrower than this and decoration costs more than it conveys.
MIN_DECORATED_WIDTH = 30

_UNICODE_GLYPHS = {
    "rule": "─",
    "sep": " · ",
    "ok": "✓",
    "fail": "✗",
    "skip": "•",
    "arrow": "▸",
    "ellipsis": "…",
    "bar": "─━",   # tqdm fill progression: empty, filled
}

_ASCII_GLYPHS = {
    "rule": "-",
    "sep": " | ",
    "ok": "+",
    "fail": "x",
    "skip": "-",
    "arrow": ">",
    "ellipsis": "...",
    "bar": "-#",
}

_ANSI = {
    "dim": "\033[2m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "red": "\033[31m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "reset": "\033[0m",
}


def terminal_width() -> int:
    """Current terminal width, re-read on every call so resizing is picked up."""
    return shutil.get_terminal_size((FALLBACK_WIDTH, 24)).columns


def use_ascii() -> bool:
    """
    True when box-drawing characters should be avoided.

    Output is reconfigured to UTF-8 at startup so encoding always succeeds, but
    a legacy Windows console still cannot *render* these glyphs. YTDOWNLOAD_ASCII
    is the escape hatch for those terminals.
    """
    return bool(os.environ.get("YTDOWNLOAD_ASCII"))


def glyphs() -> dict:
    return _ASCII_GLYPHS if use_ascii() else _UNICODE_GLYPHS


def use_color(stream=None) -> bool:
    """
    Colour only when writing to a real terminal.

    Honours NO_COLOR (https://no-color.org) and FORCE_COLOR so redirected or
    piped output stays free of escape sequences.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    stream = stream if stream is not None else sys.stdout
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError):
        return False


def paint(text: str, *styles: str) -> str:
    """Wrap text in ANSI styles, or return it unchanged when colour is off."""
    if not styles or not use_color():
        return text
    prefix = "".join(_ANSI.get(s, "") for s in styles)
    return f"{prefix}{text}{_ANSI['reset']}" if prefix else text


def char_width(char: str) -> int:
    """
    Columns a single character occupies.

    Counting characters is not the same as counting columns: yt-dlp rewrites
    ASCII quotes in titles as fullwidth quotes (U+FF02), which are East Asian
    "Fullwidth" and take two columns each. Measuring them as one made lines
    that were supposedly flush with the terminal wrap by a couple of columns.
    """
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def display_width(text: str) -> int:
    """Columns `text` occupies when rendered."""
    return sum(char_width(c) for c in text)


def _take(text: str, columns: int) -> str:
    """Longest prefix of text fitting in `columns` display columns."""
    out, used = [], 0
    for char in text:
        w = char_width(char)
        if used + w > columns:
            break
        out.append(char)
        used += w
    return "".join(out)


def _take_end(text: str, columns: int) -> str:
    """Longest suffix of text fitting in `columns` display columns."""
    out, used = [], 0
    for char in reversed(text):
        w = char_width(char)
        if used + w > columns:
            break
        out.append(char)
        used += w
    return "".join(reversed(out))


def truncate(text: str, limit: int) -> str:
    """
    Shorten text to `limit` display columns, eliding the middle.

    The middle is dropped rather than the tail because both ends carry the
    identifying information: the channel at the front, the video id and
    extension at the back.
    """
    ellipsis = glyphs()["ellipsis"]
    if limit <= 0 or display_width(text) <= limit:
        return text

    ellipsis_width = display_width(ellipsis)
    if limit <= ellipsis_width:
        return _take(text, limit)

    keep = limit - ellipsis_width
    head_columns = (keep + 1) // 2
    tail_columns = keep - head_columns
    head = _take(text, head_columns)
    tail = _take_end(text, tail_columns) if tail_columns else ""
    return head + ellipsis + tail


def write(text: str = ""):
    """
    Print without corrupting an active progress bar.

    tqdm.write clears the bar, emits the line and repaints; a bare print()
    interleaves with the bar's carriage returns and leaves fragments behind.
    """
    tqdm.write(text)


def rule(label: str = "") -> str:
    """
    A horizontal rule filling the current terminal width, optionally labelled:

        -- 1/6 --------------------------------------------
    """
    width = terminal_width()
    char = glyphs()["rule"]
    if not label:
        return char * width

    prefix = char * 2
    head = f"{prefix} {label} "
    head_width = display_width(head)
    if head_width >= width:
        return truncate(head, width)
    return head + char * (width - head_width)


def block_header(index: int, total: int, url: str) -> str:
    """Opening lines of a per-video block: a labelled rule plus the source URL."""
    header = paint(rule(f"{index}/{total}"), "dim")
    return f"{header}\n  {paint(truncate(url, terminal_width() - 2), 'dim')}"


def field(text: str, indent: int = 2) -> str:
    """An indented detail line, truncated to fit the current width."""
    return " " * indent + truncate(text, max(terminal_width() - indent, 1))


def status(symbol_key: str, text: str, *styles: str, indent: int = 2) -> str:
    """An indented status line such as '  ✓ saved · 16.7 MB'."""
    symbol = glyphs()[symbol_key]
    room = max(terminal_width() - indent - display_width(symbol) - 1, 1)
    return " " * indent + paint(f"{symbol} {truncate(text, room)}", *styles)


def separator() -> str:
    return glyphs()["sep"]


def human_size(num_bytes: int) -> str:
    """Render a byte count compactly (1.4 GB, 16.7 MB, 812 KB)."""
    if num_bytes is None:
        return "unknown"
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def progress_bar(label: str = "", total=100, unit: str = "") -> tqdm:
    """
    A width-adaptive progress bar. Update its trailing text with set_status().

    dynamic_ncols re-reads the terminal width on every refresh, so the bar
    reflows when the window is resized. A fixed ncols writes lines wider than
    the terminal, which wrap and leave a trail of fragments behind because the
    carriage return only rewinds the final physical line.

    The trailing text rides in {desc}, not {postfix}: tqdm unconditionally
    prepends ", " to postfix (format_meter does
    `postfix = ', ' + postfix if postfix else ''`), which shows up as a stray
    comma between the bar and the speed.

    leave=False keeps finished bars from stacking up over a multi-video batch.
    """
    bar = tqdm(
        total=total,
        unit=unit,
        dynamic_ncols=True,
        leave=False,
        bar_format="  {percentage:3.0f}% {bar}  {desc}",
        ascii=glyphs()["bar"],
    )
    if label:
        bar.set_description_str(label)
    return bar


def set_status(bar, text: str):
    """Set the text trailing a progress bar."""
    bar.set_description_str(text)
