from src import loggingtool
import os

# setup logging tests
def test_setup_logging_creates_file(tmp_path):
    log_dir = tmp_path / "logs"

    log_file = loggingtool.setup_logging(str(log_dir), keep_last=5)

    # Check file exists
    assert os.path.exists(log_file)

    # Check filename format
    assert "download_" in os.path.basename(log_file)
    assert log_file.endswith(".log")

# setup logging cleanup tests
def test_cleanup_keeps_only_keep_last(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # Create 10 fake old log files
    for i in range(10):
        file = log_dir / f"old_{i}.log"
        file.write_text("test")

    # Run setup_logging with keep_last=3
    loggingtool.setup_logging(str(log_dir), keep_last=3)

    remaining_logs = list(log_dir.glob("*.log"))

    # Should keep only 3 logs
    assert len(remaining_logs) == 3

# Check that the remaining logs are the newest ones
def test_cleanup_ignores_delete_errors(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # Create 6 log files
    for i in range(6):
        file = log_dir / f"old_{i}.log"
        file.write_text("test")

    # Force os.remove to fail
    def fake_remove(path):
        raise PermissionError("Cannot delete")

    monkeypatch.setattr(loggingtool.os, "remove", fake_remove)

    # Should not raise
    loggingtool.setup_logging(str(log_dir), keep_last=2)

# Check that the log file contains the start message
def test_log_contains_start_message(tmp_path):
    log_dir = tmp_path / "logs"

    log_file = loggingtool.setup_logging(str(log_dir), keep_last=5)

    with open(log_file, "r") as f:
        content = f.read()

    assert "Download session started" in content

