"""Step 6: Create archive directory structure on external drive."""
import os, sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

DIRS = [
    "raw",
    "proxy/low_fps",
    "proxy/high_fps",
    "audio",
    "exports",
    "merged",
    "logs",
]

def main():
    archive_root = os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive")

    if not os.path.exists(archive_root):
        print(f"FAIL: Archive root not found — {archive_root}")
        print("      Mount the external drive first.")
        sys.exit(1)

    for d in DIRS:
        full_path = os.path.join(archive_root, d)
        os.makedirs(full_path, exist_ok=True)
        print(f"  OK  {full_path}")

    print(f"\nPASS: Archive structure ready under {archive_root}")

if __name__ == "__main__":
    main()
