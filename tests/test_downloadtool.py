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

# next video filename tests
def test_next_video_filename(tmp_path):
    folder = tmp_path

    # Create fake existing file
    (folder / "video001.mp4").touch()

    result = downloadtool.get_next_video_filename(str(folder))

    assert result.endswith("video002.mp4")

# convert audio to aac tests
def test_ffprobe_failure(monkeypatch):

    def fake_check_output(*args, **kwargs):
        raise subprocess.CalledProcessError(1, "ffprobe")

    monkeypatch.setattr(subprocess, "check_output", fake_check_output)

    with pytest.raises(RuntimeError):
        downloadtool.convert_audio_to_aac("fake.mp4")