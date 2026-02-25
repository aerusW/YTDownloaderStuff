import os
import logging
from datetime import datetime


def setup_logging(log_base_folder: str, keep_last: int = 5) -> str:
    """
    Setup logging system.

    - Creates log folder if it does not exist
    - Creates timestamped log file
    - Keeps only the newest `keep_last` log files
    - Returns the created log file path
    """

    os.makedirs(log_base_folder, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_base_folder, f"download_{timestamp}.log")

    # Reset root logger completely (important if re-imported)
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    logging.basicConfig(
        filename=log_file,
        level=logging.WARNING,
        format="%(asctime)s - %(levelname)s - %(message)s",
        filemode="w"
    )

    logging.warning("=== Download session started ===")

    _cleanup_old_logs(log_base_folder, keep_last)

    return log_file


def _cleanup_old_logs(log_folder: str, keep_last: int):
    """
    Keep only the newest `keep_last` .log files.
    """

    log_files = sorted(
        [
            os.path.join(log_folder, f)
            for f in os.listdir(log_folder)
            if f.endswith(".log")
        ],
        key=os.path.getmtime
    )

    if len(log_files) > keep_last:
        for old_file in log_files[:-keep_last]:
            try:
                os.remove(old_file)
            except Exception:
                pass
