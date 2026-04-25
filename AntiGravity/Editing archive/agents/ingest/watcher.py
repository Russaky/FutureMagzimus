"""INGEST Agent — watches raw/ for new video files and triggers the pipeline."""
import os, sys, time, logging
from pathlib import Path
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

load_dotenv(Path(__file__).parents[2] / ".env")

ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))
RAW_DIR = ARCHIVE_ROOT / "raw"
LOG_DIR = Path(__file__).parents[2] / "logs"
LOG_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [INGEST] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "ingest.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".mts", ".m2ts", ".avi", ".mkv"}
UNSORTED_FOLDER = "unsorted"

# Minimum file size before processing (avoid partial writes)
MIN_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10MB
STABLE_WAIT_SECONDS = 5  # wait for file to stop growing


def is_stable(path: Path, wait: int = STABLE_WAIT_SECONDS) -> bool:
    """Return True if file size hasn't changed in `wait` seconds."""
    try:
        size1 = path.stat().st_size
        time.sleep(wait)
        size2 = path.stat().st_size
        return size1 == size2 and size2 >= MIN_FILE_SIZE_BYTES
    except Exception:
        return False


class VideoHandler(FileSystemEventHandler):
    def __init__(self):
        self._processing = set()

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return
        if path in self._processing:
            return
        self._processing.add(path)
        self._handle(path)
        self._processing.discard(path)

    def _handle(self, path: Path):
        # Determine event_type from parent folder name
        event_type = path.parent.name

        if event_type == UNSORTED_FOLDER:
            log.warning(f"UNSORTED file detected — skipping: {path.name}")
            log.warning("Move file to a named subfolder (e.g. raw/birthday_party/) to process.")
            return

        log.info(f"New file detected: {path.name} | folder={event_type}")

        if not is_stable(path):
            log.warning(f"File not stable or too small — skipping: {path.name}")
            return

        log.info(f"File stable. Starting full pipeline for: {path.name}")

        # Import here to keep watcher lightweight
        from agents.orchestrator.pipeline import run as run_full_pipeline
        try:
            run_full_pipeline(path, event_type)
        except Exception as e:
            log.error(f"Pipeline failed for {path.name}: {e}")


def main():
    if not RAW_DIR.exists():
        log.error(f"raw/ directory not found: {RAW_DIR}")
        log.error("Is the external drive mounted?")
        sys.exit(1)

    log.info(f"Watching: {RAW_DIR}")
    log.info("Drop video files into named subfolders of raw/ to start processing.")
    log.info("Files in raw/unsorted/ will be logged but NOT processed.")

    handler = VideoHandler()
    observer = Observer()
    observer.schedule(handler, str(RAW_DIR), recursive=True)
    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping watcher.")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
