import pytest 
import src.downloadtool as downloadtool
import subprocess

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

# convert audio to aac tests
def test_ffprobe_failure(monkeypatch):

    def fake_check_output(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffprobe")

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    with pytest.raises(RuntimeError):
        downloadtool.convert_audio_to_aac("fake.mp4")