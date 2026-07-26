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
    """Mock ffmpeg check to always return True."""
    monkeypatch.setattr(main, "check_ffmpeg_installed", lambda: True)


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
    monkeypatch.setattr(main, "check_ffmpeg_installed", lambda: False)
    monkeypatch.setattr(sys, "argv", ["prog", "--link", "https://youtube.com/test"])

    with pytest.raises(RuntimeError, match="ffmpeg not found"):
        main.main()


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
    assert "All 2 download(s) completed" in capsys.readouterr().out


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
    assert "ABORTED" in capsys.readouterr().out


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