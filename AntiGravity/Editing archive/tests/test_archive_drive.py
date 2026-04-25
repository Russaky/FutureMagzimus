"""Test 6: External drive mounted and writable."""
import os, sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def main():
    archive_root = os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive")

    if not os.path.exists(archive_root):
        print(f"FAIL: Archive root not found — {archive_root}")
        print("      Is the external drive mounted? Check Finder.")
        sys.exit(1)

    test_file = os.path.join(archive_root, "_write_test.tmp")
    try:
        with open(test_file, "w") as f:
            f.write("ok")
        os.remove(test_file)
        print(f"PASS: External drive mounted and writable — {archive_root}")
    except Exception as e:
        print(f"FAIL: Drive exists but not writable — {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
