import os
import shutil
import time

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from src.pipeline import run_acta_pipeline

_INPUT_DIR = "input"
_PROCESSED_DIR = os.path.join(_INPUT_DIR, "processed")


def process_file(path: str) -> None:
    print(f"Processing: {path}")

    result = run_acta_pipeline(path, source_filename=os.path.basename(path))
    print(f"Extracted metadata: {result['metadata']!r}")
    print(f"Generated: {result['pdf_path']}")

    os.makedirs(_PROCESSED_DIR, exist_ok=True)
    shutil.move(path, os.path.join(_PROCESSED_DIR, os.path.basename(path)))


class DocxHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        if event.src_path.endswith(".docx"):
            try:
                process_file(event.src_path)
            except Exception as e:
                print(f"Error processing {event.src_path}: {e}")


if __name__ == "__main__":
    os.makedirs(_INPUT_DIR, exist_ok=True)
    os.makedirs("output", exist_ok=True)

    observer = Observer()
    observer.schedule(DocxHandler(), path=_INPUT_DIR, recursive=False)
    observer.start()
    print(f"Watching {_INPUT_DIR}/ for .docx files...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()

    observer.join()
