import os
import pytest
import builtins
from unittest.mock import MagicMock
import sys

import YTDownload as main  # Change if your file/module is named differently


# ---------------------------
# Fixtures for mocking
# ---------------------------

@pytest.fixture
def mock_config(monkeypatch, tmp_path):
    """Mock configmanager.load_config to return predictable values."""
    fake_config = {
        "default_download_folder": str(tmp_path / "downloads"),
        "default_log_folder": str(tmp_path / "logs"),
        "default_segments": 8,
        "default_connections": 8,
        "default_segment_size": 2,
        "concurrent_segments": 5,
    }
    monkeypatch.setattr(main.configmanager, "load_config", lambda: fake_config)
    return fake_config


@pytest.fixture
def mock_logging(monkeypatch):
    """Mock logging setup."""
    monkeypatch.setattr(main.loggingtool, "setup_logging", lambda folder: "fake_log.log")


@pytest.fixture
def mock_download(monkeypatch):
    """Mock download functions."""
    monkeypatch.setattr(main.downloadtool, "get_next_video_filename", lambda folder, ext="mp4": f"video_001.{ext}")
    mock_download_video = MagicMock()
    monkeypatch.setattr(main.downloadtool, "download_video", mock_download_video)
    return mock_download_video


@pytest.fixture
def mock_ffmpeg(monkeypatch):
    """Pretend every external tool is installed and working."""
    monkeypatch.setattr(main, "check_dependencies", lambda: [])


# ---------------------------
# Basic tests
# ---------------------------

def test_main_with_link_flag(monkeypatch, mock_config, mock_logging, mock_download, mock_ffmpeg):
    test_args = [
        "prog",
        "--link", "https://youtube.com/test",
        "--quality", "720"
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    main.main()

    mock_download.assert_called_once()
    args, kwargs = mock_download.call_args
    assert args[0] == "https://youtube.com/test"
    assert args[1] == "720"


def test_main_prompts_for_input(monkeypatch, mock_config, mock_logging, mock_download, mock_ffmpeg):
    monkeypatch.setattr(sys, "argv", ["prog"])
    monkeypatch.setattr(builtins, "input", lambda _: "https://youtube.com/frominput")

    main.main()

    mock_download.assert_called_once()
    args, kwargs = mock_download.call_args
    assert args[0] == "https://youtube.com/frominput"


def test_main_no_url_provided(monkeypatch, mock_config, mock_logging, mock_ffmpeg):
    monkeypatch.setattr(sys, "argv", ["prog"])
    monkeypatch.setattr(builtins, "input", lambda _: "")

    with pytest.raises(RuntimeError, match="No URL provided"):
        main.main()


def test_ffmpeg_not_installed(monkeypatch, mock_config):
    monkeypatch.setattr(main, "check_dependencies", lambda: ["ffmpeg"])
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/test"])

    with pytest.raises(RuntimeError, match="missing dependencies: ffmpeg"):
        main.main()


def test_missing_aria2c_reported(monkeypatch, mock_config, capsys):
    """aria2c used to fail deep inside the download; it must be caught up front."""
    monkeypatch.setattr(main, "check_dependencies", lambda: ["aria2c", "ffprobe"])
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/test"])

    with pytest.raises(RuntimeError, match="aria2c, ffprobe"):
        main.main()

    out = capsys.readouterr().out
    assert "aria2c" in out and "aria2.github.io" in out


def test_check_binary_rejects_missing(monkeypatch):
    monkeypatch.setattr(main.shutil, "which", lambda name: None)
    assert main.check_binary("ffmpeg") is False


def test_check_binary_rejects_nonzero_exit(monkeypatch):
    """Present but broken must not count as installed."""
    monkeypatch.setattr(main.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(main.subprocess, "run",
                        lambda *a, **kw: MagicMock(returncode=1))
    assert main.check_binary("ffmpeg") is False


def test_check_binary_accepts_working(monkeypatch):
    monkeypatch.setattr(main.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    monkeypatch.setattr(main.subprocess, "run",
                        lambda *a, **kw: MagicMock(returncode=0))
    assert main.check_binary("ffmpeg") is True


def test_check_binary_uses_correct_version_flag(monkeypatch):
    """
    'aria2c -version' is a parse error and 'yt-dlp -version' means --verbose,
    so the single-dash ffmpeg convention must not be applied to them.
    """
    seen = {}

    def record(cmd, **kwargs):
        seen[cmd[0]] = cmd[1]
        return MagicMock(returncode=0)

    monkeypatch.setattr(main.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(main.subprocess, "run", record)

    for name in main.REQUIRED_BINARIES:
        main.check_binary(name)

    assert seen["ffmpeg"] == "-version"
    assert seen["ffprobe"] == "-version"
    assert seen["yt-dlp"] == "--version"
    assert seen["aria2c"] == "--version"


# ---------------------------
# Tests for all other flags
# ---------------------------

def test_all_flags(monkeypatch, mock_config, mock_logging, mock_download, mock_ffmpeg, tmp_path):
    """Test all CLI flags together."""
    urls = ["https://youtube.com/video1", "https://youtube.com/video2"]
    custom_folder = str(tmp_path / "custom_folder")
    custom_log = str(tmp_path / "custom_log")

    test_args = [
        "prog",
        "--link", urls[0],
        "--link", urls[1],
        "--quality", "4k",
        "--folder", custom_folder,
        "--log-folder", custom_log,
        "--segments", "12",
        "--connections", "6",
        "--segment-size", "10",
        "--concurrent-segments", "7",
        "--do-not-convert",
        "--verbose"
    ]
    monkeypatch.setattr(sys, "argv", test_args)

    main.main()

    # It should call download_video twice (one per URL)
    assert mock_download.call_count == 2

    # Check first call
    args1, kwargs1 = mock_download.call_args_list[0]
    assert args1[0] == urls[0]
    assert args1[1] == "4k"
    assert kwargs1["skip_conversion"] is True
    assert kwargs1["verbose"] is True
    assert kwargs1["final_segments"] == 12 if "final_segments" in kwargs1 else True
    assert kwargs1["final_connections"] == 6 if "final_connections" in kwargs1 else True
    assert kwargs1["final_segment_size"] == 10 if "final_segment_size" in kwargs1 else True
    assert kwargs1["final_concurrent_segments"] == 7 if "final_concurrent_segments" in kwargs1 else True

    # Check second call
    args2, kwargs2 = mock_download.call_args_list[1]
    assert args2[0] == urls[1]


# ---------------------------
# Batch resilience
# ---------------------------

def test_batch_continues_after_failure(monkeypatch, mock_config, mock_logging, mock_ffmpeg, capsys):
    """A failing URL must not abandon the URLs after it."""
    urls = ["https://youtube.com/bad", "https://youtube.com/good1", "https://youtube.com/good2"]

    def flaky_download(url, *args, **kwargs):
        if url.endswith("bad"):
            raise RuntimeError("Download failed")

    monkeypatch.setattr(main.downloadtool, "get_next_video_filename",
                        lambda folder, ext="mp4": f"video_001.{ext}")
    mock_dl = MagicMock(side_effect=flaky_download)
    monkeypatch.setattr(main.downloadtool, "download_video", mock_dl)
    monkeypatch.setattr(sys, "argv", ["prog"] + [a for u in urls for a in ("--link", u)])

    exit_code = main.main()

    # All three were attempted despite the first one failing
    assert mock_dl.call_count == 3
    assert [c.args[0] for c in mock_dl.call_args_list] == urls

    # Non-zero exit and the failing URL named in the summary
    assert exit_code == 1
    out = capsys.readouterr().out
    assert "1 failed" in out
    assert "https://youtube.com/bad" in out


def test_batch_all_success_returns_zero(monkeypatch, mock_config, mock_logging,
                                        mock_download, mock_ffmpeg, capsys):
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/a",
                                      "--link", "https://youtube.com/b"])

    exit_code = main.main()

    assert exit_code == 0
    assert mock_download.call_count == 2
    assert "2 downloaded" in capsys.readouterr().out


def test_keyboard_interrupt_stops_batch(monkeypatch, mock_config, mock_logging,
                                        mock_ffmpeg, capsys):
    """Ctrl-C is deliberate: stop the batch rather than plough on."""
    urls = ["https://youtube.com/a", "https://youtube.com/b", "https://youtube.com/c"]

    monkeypatch.setattr(main.downloadtool, "get_next_video_filename",
                        lambda folder, ext="mp4": f"video_001.{ext}")
    mock_dl = MagicMock(side_effect=KeyboardInterrupt())
    monkeypatch.setattr(main.downloadtool, "download_video", mock_dl)
    monkeypatch.setattr(sys, "argv", ["prog"] + [a for u in urls for a in ("--link", u)])

    exit_code = main.main()

    assert mock_dl.call_count == 1  # stopped, did not attempt b and c
    assert exit_code == 1
    assert "interrupted" in capsys.readouterr().out


# ---------------------------
# Download archive
# ---------------------------

def test_archive_defaults_into_download_folder(monkeypatch, mock_config, mock_logging,
                                               mock_download, mock_ffmpeg, tmp_path):
    folder = str(tmp_path / "vids")
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--link", "https://youtube.com/a", "--folder", folder])

    main.main()

    archive = mock_download.call_args.kwargs["download_archive"]
    assert archive.endswith(".download-archive.txt")
    assert os.path.dirname(archive) == os.path.abspath(folder)


def test_no_archive_disables_dedup(monkeypatch, mock_config, mock_logging,
                                   mock_download, mock_ffmpeg):
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--link", "https://youtube.com/a", "--no-archive"])

    main.main()

    assert mock_download.call_args.kwargs["download_archive"] is None


def test_explicit_archive_path_wins(monkeypatch, mock_config, mock_logging,
                                    mock_download, mock_ffmpeg, tmp_path):
    custom = str(tmp_path / "my-archive.txt")
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--link", "https://youtube.com/a", "--archive", custom])

    main.main()

    assert mock_download.call_args.kwargs["download_archive"] == custom


def test_skipped_downloads_counted_separately(monkeypatch, mock_config, mock_logging,
                                              mock_ffmpeg, capsys):
    """download_video returns None when the video was already archived."""
    monkeypatch.setattr(main.downloadtool, "get_next_video_filename",
                        lambda folder, ext="mp4": f"video_001.{ext}")
    monkeypatch.setattr(main.downloadtool, "download_video",
                        MagicMock(return_value=None))
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/a",
                                      "--link", "https://youtube.com/b"])

    exit_code = main.main()

    assert exit_code == 0
    assert "2 skipped" in capsys.readouterr().out


# ---------------------------
# Naming
# ---------------------------

def test_descriptive_naming_is_the_default(monkeypatch, mock_config, mock_logging,
                                           mock_download, mock_ffmpeg, tmp_path):
    folder = str(tmp_path / "vids")
    monkeypatch.setattr(sys, "argv",
                        ["prog", "--link", "https://youtube.com/a", "--folder", folder])

    main.main()

    template = mock_download.call_args.kwargs["output_template"]
    assert template is not None
    assert os.path.dirname(template) == os.path.abspath(folder)
    assert "%(title)" in template and "%(id)s" in template
    assert "%(channel" in template


def test_sequential_names_opt_in(monkeypatch, mock_config, mock_logging,
                                 mock_download, mock_ffmpeg):
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/a",
                                      "--sequential-names"])

    main.main()

    assert mock_download.call_args.kwargs["output_template"] is None


def test_custom_output_template(monkeypatch, mock_config, mock_logging,
                                mock_download, mock_ffmpeg):
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/a",
                                      "--output-template", "%(id)s.%(ext)s"])

    main.main()

    assert mock_download.call_args.kwargs["output_template"].endswith("%(id)s.%(ext)s")


def test_metadata_embedded_by_default(monkeypatch, mock_config, mock_logging,
                                      mock_download, mock_ffmpeg):
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/a"])
    main.main()
    assert mock_download.call_args.kwargs["embed_metadata"] is True


def test_no_metadata_flag(monkeypatch, mock_config, mock_logging,
                          mock_download, mock_ffmpeg):
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/a",
                                      "--no-metadata"])
    main.main()
    assert mock_download.call_args.kwargs["embed_metadata"] is False


# ---------------------------
# Console encoding
# ---------------------------

def test_non_cp1252_title_does_not_fail_the_download(monkeypatch, mock_config,
                                                     mock_logging, mock_ffmpeg):
    """
    Regression: yt-dlp rewrites ASCII quotes in titles as fullwidth quotes
    (U+FF02). Printing that name to a cp1252 Windows console raised
    UnicodeEncodeError, so a download that had already succeeded was caught by
    the per-URL handler and reported as a failure.
    """
    import io

    saved_name = 'Fireship - The most interesting ＂hack＂ [abc].mp4'
    monkeypatch.setattr(main.downloadtool, "get_next_video_filename",
                        lambda folder, ext="mp4": f"video_001.{ext}")
    monkeypatch.setattr(main.downloadtool, "download_video",
                        MagicMock(return_value=saved_name))
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/a"])

    # A console that cannot encode U+FF02, as on stock Windows
    buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout",
                        io.TextIOWrapper(buffer, encoding="cp1252", errors="strict"))

    exit_code = main.main()

    sys.stdout.flush()
    assert exit_code == 0, "successful download must not be reported as a failure"


def test_configure_console_encoding_survives_odd_streams(monkeypatch):
    """Must not explode when stdout is not a reconfigurable text stream."""
    class NoReconfigure:
        pass

    monkeypatch.setattr(sys, "stdout", NoReconfigure())
    monkeypatch.setattr(sys, "stderr", NoReconfigure())
    main.configure_console_encoding()  # no exception


def test_version_flag(monkeypatch):
    """Test that --version prints the version and exits."""
    from io import StringIO
    import contextlib

    monkeypatch.setattr(sys, "argv", ["prog", "--version"])

    with pytest.raises(SystemExit) as e:
        with contextlib.redirect_stdout(StringIO()) as f:
            main.main()

    assert str(main.version) in f.getvalue()
    assert e.type == SystemExit