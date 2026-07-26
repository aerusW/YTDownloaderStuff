import os
import pytest
import src.downloadtool as downloadtool
import subprocess


# ---------------------------------------------------------------
# Harness: run download_video() against a fake yt-dlp subprocess so
# the constructed command line can be asserted on.
# ---------------------------------------------------------------

def fake_ytdlp(recorded_commands, produced_file, stdout_lines=(), returncode=0):
    class FakeProcess:
        def __init__(self, command, **kwargs):
            recorded_commands.append(command)
            # Emulate yt-dlp's --print-to-file after_move:%(filepath)s
            if "--print-to-file" in command and produced_file is not None:
                report = command[command.index("--print-to-file") + 2]
                with open(report, "w", encoding="utf-8") as f:
                    f.write(str(produced_file) + "\n")
            self.stdout = iter(stdout_lines)
            self.returncode = returncode

        def wait(self):
            return self.returncode

        def kill(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    return FakeProcess


def run_download(monkeypatch, tmp_path, quality="1080", produced_name="video001.mkv",
                 audio_codec="opus", **kwargs):
    """Invoke download_video() with a fake subprocess; return the command it built."""
    produced = tmp_path / produced_name
    produced.write_bytes(b"fake")
    recorded = []
    monkeypatch.setattr(downloadtool.subprocess, "Popen",
                        fake_ytdlp(recorded, produced))
    # Keep the assertion focused on the yt-dlp command, not on ffprobe.
    monkeypatch.setattr(downloadtool, "probe_audio_codec", lambda path: audio_codec)
    result = downloadtool.download_video(
        "https://youtu.be/abc123", quality, str(tmp_path / "video001.mp4"),
        segments=16, max_connections=16, segment_size=4, concurrent_segments=10,
        **kwargs
    )
    return recorded[0], result

# build format string tests
def test_build_format_string_4k():
    result = downloadtool.build_format_string("4k")
    assert "2160" in result

def test_build_format_string_720():
    result = downloadtool.build_format_string("720")
    assert "720" in result

def test_build_format_string_default():
    result = downloadtool.build_format_string("something_else")
    assert "1080" in result

def test_build_format_string_premium():
    # Premium targets YouTube's enhanced 1080p VP9 stream (format 616)
    result = downloadtool.build_format_string("premium")
    assert "616" in result

def test_premium_fallback_pins_vp9():
    """
    Regression: the old chain fell back to an uncodeced bestvideo, so without
    cookies it silently produced AV1 while the docs promised VP9.
    """
    result = downloadtool.build_format_string("premium")
    tiers = result.split("/")
    assert tiers[0].startswith("616")
    # The tier right after 616 must constrain the codec to VP9
    assert "vp0?9" in tiers[1] or "vp9" in tiers[1]
    assert "height<=1080" in tiers[1]

def test_premium_fallback_matches_both_vp9_spellings():
    """YouTube reports VP9 as bare 'vp9' or ISO-style 'vp09.00.40.08'."""
    import re
    result = downloadtool.build_format_string("premium")
    pattern = re.search(r"vcodec~='([^']+)'", result)
    assert pattern, "expected a regex codec filter"
    regex = re.compile(pattern.group(1))
    assert regex.match("vp9")
    assert regex.match("vp09.00.40.08")
    assert not regex.match("av01.0.08M.08")
    assert not regex.match("avc1.640028")

def test_premium_chain_degrades_to_any_format():
    result = downloadtool.build_format_string("premium")
    assert result.split("/")[-1] == "b"

# container selection tests
def test_container_premium_is_mkv():
    assert downloadtool.container_for_quality("premium") == "mkv"

def test_container_default_is_mp4():
    assert downloadtool.container_for_quality("1080") == "mp4"

# next video filename tests
def test_next_video_filename(tmp_path):
    folder = tmp_path

    # Create fake existing file
    (folder / "video001.mp4").touch()

    result = downloadtool.get_next_video_filename(str(folder))

    assert result.endswith("video002.mp4")

def test_next_video_filename_mkv_ext(tmp_path):
    result = downloadtool.get_next_video_filename(str(tmp_path), ext="mkv")
    assert result.endswith("video001.mkv")

# Regression: a slot is taken regardless of which extension occupies it
def test_next_video_filename_skips_other_extensions(tmp_path):
    (tmp_path / "video001.mkv").touch()
    result = downloadtool.get_next_video_filename(str(tmp_path), ext="mp4")
    assert result.endswith("video002.mp4")

def test_next_video_filename_skips_mixed_extensions(tmp_path):
    for name in ("video001.mkv", "video002.mp4", "video003.webm"):
        (tmp_path / name).touch()
    result = downloadtool.get_next_video_filename(str(tmp_path), ext="mkv")
    assert result.endswith("video004.mkv")

def test_next_video_filename_handles_glob_chars_in_folder(tmp_path):
    folder = tmp_path / "my [videos]"
    folder.mkdir()
    (folder / "video001.mkv").touch()
    result = downloadtool.get_next_video_filename(str(folder), ext="mp4")
    assert result.endswith("video002.mp4")

# aac temp path tests
def test_aac_temp_path_basic():
    assert downloadtool.aac_temp_path("/videos/video001.mp4") == "/videos/video001_aac.mp4"

def test_aac_temp_path_preserves_directory_containing_extension():
    """Regression: str.replace() rewrote the folder name too."""
    result = downloadtool.aac_temp_path(r"D:\clips.mp4.old\video001.mp4")
    assert result == r"D:\clips.mp4.old\video001_aac.mp4"
    assert "clips.mp4.old" in result

def test_aac_temp_path_non_mp4_extension():
    assert downloadtool.aac_temp_path("/v/a.mkv") == "/v/a_aac.mkv"

# reported output path tests
def test_read_reported_path(tmp_path):
    report = tmp_path / "filepath.txt"
    report.write_text("C:\\videos\\video001.mkv\n", encoding="utf-8")
    assert downloadtool.read_reported_path(str(report)) == "C:\\videos\\video001.mkv"

def test_read_reported_path_uses_last_line(tmp_path):
    report = tmp_path / "filepath.txt"
    report.write_text("first.mp4\nsecond.mkv\n", encoding="utf-8")
    assert downloadtool.read_reported_path(str(report)) == "second.mkv"

def test_read_reported_path_empty_file(tmp_path):
    report = tmp_path / "filepath.txt"
    report.write_text("\n  \n", encoding="utf-8")
    assert downloadtool.read_reported_path(str(report)) == ""

def test_read_reported_path_missing_file(tmp_path):
    assert downloadtool.read_reported_path(str(tmp_path / "nope.txt")) == ""

# command construction tests
def test_command_disables_playlist_expansion(monkeypatch, tmp_path):
    """A URL carrying &list= must download one video, not the whole playlist."""
    command, _ = run_download(monkeypatch, tmp_path)
    assert "--no-playlist" in command

def test_command_reports_final_path(monkeypatch, tmp_path):
    command, result = run_download(monkeypatch, tmp_path)
    assert "--print-to-file" in command
    idx = command.index("--print-to-file")
    assert command[idx + 1] == "after_move:%(filepath)s"
    # download_video returns the path yt-dlp reported, not the predicted one
    assert result == str(tmp_path / "video001.mkv")

# audio codec probing tests
def test_probe_audio_codec(monkeypatch):
    monkeypatch.setattr(downloadtool.subprocess, "check_output",
                        lambda *a, **kw: b"opus\n")
    assert downloadtool.probe_audio_codec("x.mkv") == "opus"

def test_probe_audio_codec_handles_failure(monkeypatch):
    def boom(*a, **kw):
        raise subprocess.CalledProcessError(1, "ffprobe")
    monkeypatch.setattr(downloadtool.subprocess, "check_output", boom)
    assert downloadtool.probe_audio_codec("x.mkv") == "unknown"

def test_probe_audio_codec_handles_missing_binary(monkeypatch):
    def boom(*a, **kw):
        raise FileNotFoundError("ffprobe")
    monkeypatch.setattr(downloadtool.subprocess, "check_output", boom)
    assert downloadtool.probe_audio_codec("x.mkv") == "unknown"

def test_probe_audio_codec_empty_output(monkeypatch):
    monkeypatch.setattr(downloadtool.subprocess, "check_output", lambda *a, **kw: b"\n")
    assert downloadtool.probe_audio_codec("x.mkv") == "unknown"

def test_no_ytdlp_python_api_dependency():
    """
    The download path shells out to the yt-dlp binary only. Importing the
    Python package too meant both had to be installed and version-matched,
    and every video paid for two extractions (n-challenge solved twice).
    """
    import inspect
    source = inspect.getsource(downloadtool)
    assert "YoutubeDL" not in source
    assert "yt_dlp" not in source

# convert audio to aac tests
def test_ffprobe_failure(monkeypatch):

    def fake_check_output(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffprobe")

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    with pytest.raises(RuntimeError):
        downloadtool.convert_audio_to_aac("fake.mp4")