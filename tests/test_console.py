import os
import shutil
import pytest

from src import console


@pytest.fixture
def width(monkeypatch):
    """Set a fake terminal width; returns a setter so a test can resize mid-run."""
    def _set(columns):
        monkeypatch.setattr(console.shutil, "get_terminal_size",
                            lambda fallback=None: os.terminal_size((columns, 24)))
    _set(80)
    return _set


@pytest.fixture(autouse=True)
def plain_output(monkeypatch):
    """Colour off and unicode glyphs on, unless a test says otherwise."""
    monkeypatch.delenv("YTDOWNLOAD_ASCII", raising=False)
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.setenv("NO_COLOR", "1")


# --- width handling -------------------------------------------------------

def test_rule_fills_terminal_width(width):
    width(60)
    assert len(console.rule()) == 60

def test_labelled_rule_fills_terminal_width(width):
    width(50)
    line = console.rule("1/6")
    assert len(line) == 50
    assert "1/6" in line

def test_rule_is_reread_on_resize(width):
    """
    Regression: width must be queried per call. Caching it meant the layout
    kept the size the terminal had when the process started.
    """
    width(100)
    assert len(console.rule()) == 100
    width(40)  # user drags the window narrower mid-download
    assert len(console.rule()) == 40

def test_rule_survives_width_narrower_than_label(width):
    width(5)
    assert len(console.rule("10/10")) <= 5


# --- truncation -----------------------------------------------------------

def test_truncate_leaves_short_text_alone():
    assert console.truncate("short", 40) == "short"

def test_truncate_respects_limit():
    assert len(console.truncate("x" * 200, 30)) == 30

def test_truncate_keeps_both_ends():
    """Channel is at the front, video id and extension at the back."""
    name = "Fireship - The most interesting hack in history [KOpTWx1Eou4].mp4"
    out = console.truncate(name, 40)
    assert len(out) == 40
    assert out.startswith("Fireship")
    assert out.endswith(".mp4")
    assert "…" in out

def test_truncate_returns_text_unchanged_for_nonpositive_limit():
    """A width of 0 means "unknown"; mangling the text would help nobody."""
    assert console.truncate("hello", 0) == "hello"

def test_truncate_at_tiny_limits_never_exceeds_it():
    for limit in range(1, 6):
        assert len(console.truncate("hello world", limit)) <= limit

def test_field_fits_within_width(width):
    width(40)
    assert console.display_width(console.field("y" * 100)) <= 40

def test_status_fits_within_width(width):
    width(40)
    assert console.display_width(console.status("ok", "z" * 100)) <= 40


# --- double-width characters ----------------------------------------------

def test_fullwidth_chars_count_as_two_columns():
    """
    yt-dlp rewrites ASCII quotes in titles as fullwidth quotes (U+FF02), which
    render two columns wide. Counting them as one made lines that looked flush
    with the terminal wrap by a couple of columns.
    """
    assert console.char_width("＂") == 2
    assert console.char_width("a") == 1
    assert console.display_width("＂hack＂") == 8   # 2 + 4 + 2

def test_combining_marks_take_no_columns():
    assert console.char_width("́") == 0

def test_truncate_measures_columns_not_characters():
    title = "Fireship - The most interesting ＂hack＂ in history [KOpTWx1Eou4].mp4"
    out = console.truncate(title, 40)
    assert console.display_width(out) <= 40

def test_wide_title_line_never_exceeds_terminal(width):
    """Regression: the real filename that overflowed at width 72."""
    title = "Fireship - The most interesting ＂hack＂ in history... [KOpTWx1Eou4].mp4"
    for columns in (100, 72, 52, 36, 20):
        width(columns)
        assert console.display_width(console.field(title)) <= columns

def test_rule_accounts_for_wide_label(width):
    width(40)
    assert console.display_width(console.rule("＂1/6＂")) == 40


# --- ascii fallback -------------------------------------------------------

def test_ascii_mode_avoids_box_drawing(monkeypatch, width):
    monkeypatch.setenv("YTDOWNLOAD_ASCII", "1")
    width(40)
    line = console.rule("1/2")
    assert "─" not in line
    assert "-" in line

def test_ascii_mode_avoids_unicode_symbols(monkeypatch):
    monkeypatch.setenv("YTDOWNLOAD_ASCII", "1")
    out = console.status("ok", "saved")
    assert "✓" not in out
    assert out.encode("cp1252")  # would raise if a non-cp1252 glyph slipped in

def test_ascii_mode_ellipsis(monkeypatch):
    monkeypatch.setenv("YTDOWNLOAD_ASCII", "1")
    out = console.truncate("a" * 50, 20)
    assert "…" not in out
    assert "..." in out


# --- colour gating --------------------------------------------------------

def test_no_color_env_disables_colour(monkeypatch):
    monkeypatch.setenv("NO_COLOR", "1")
    assert console.use_color() is False
    assert "\033[" not in console.paint("text", "green")

def test_colour_disabled_when_not_a_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    class NotATty:
        def isatty(self):
            return False

    assert console.use_color(NotATty()) is False

def test_colour_enabled_for_tty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)

    class Tty:
        def isatty(self):
            return True

    assert console.use_color(Tty()) is True

def test_use_color_survives_stream_without_isatty(monkeypatch):
    monkeypatch.delenv("NO_COLOR", raising=False)
    assert console.use_color(object()) is False


# --- misc -----------------------------------------------------------------

def test_human_size():
    assert console.human_size(0) == "0 B"
    assert console.human_size(1536) == "1.5 KB"
    assert console.human_size(16_713_599).endswith("MB")
    assert console.human_size(5 * 1024**3).endswith("GB")

def test_progress_bar_is_width_adaptive():
    """
    Regression: a hardcoded ncols wrote lines wider than the terminal, which
    wrapped and left a trail of fragments because the carriage return only
    rewinds the last physical line.
    """
    bar = console.progress_bar("test")
    try:
        assert bar.dynamic_ncols, "bar must re-read terminal width on each refresh"
        assert bar.leave is False, "finished bars must not stack up over a batch"
    finally:
        bar.close()

def test_progress_bar_avoids_tqdm_postfix_comma():
    """
    Regression: tqdm's format_meter does `postfix = ', ' + postfix`, so a custom
    bar_format using {postfix} renders a stray comma between bar and speed.
    """
    bar = console.progress_bar()
    try:
        assert "{postfix}" not in bar.bar_format
        assert "{desc}" in bar.bar_format
        console.set_status(bar, "16MiB/s")
        assert ", 16MiB/s" not in str(bar)
        assert "16MiB/s" in str(bar)
    finally:
        bar.close()

def test_block_header_contains_position_and_url(width):
    width(80)
    out = console.block_header(2, 6, "https://youtu.be/abc")
    assert "2/6" in out
    assert "abc" in out
