"""Test INGEST pipeline with a synthetic 30s video file."""
import os, sys, subprocess, tempfile, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")

sys.path.insert(0, str(Path(__file__).parents[1]))

ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))


def make_test_video(output_path: Path, duration: int = 35):
    """Create a synthetic test video with ffmpeg."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=duration={duration}:size=1280x720:rate=25",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "30",
        "-c:a", "aac", "-b:a", "128k",
        "-t", str(duration),
        str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"Test video creation failed:\n{result.stderr[-300:]}")


def main():
    print("=== INGEST Pipeline Test ===")

    # 1. Check drive mounted
    if not ARCHIVE_ROOT.exists():
        print(f"FAIL: Archive root not found: {ARCHIVE_ROOT}")
        sys.exit(1)

    # 2. Create test video in raw/test_event/
    test_dir = ARCHIVE_ROOT / "raw" / "test_event"
    test_video = test_dir / "_pipeline_test.mp4"
    print(f"Creating 35s synthetic test video at: {test_video}")
    make_test_video(test_video)
    print("PASS: Test video created")

    # 3. Run pipeline (single chunk — 35s < 600s)
    from agents.ingest.pipeline import run_pipeline
    print("Running pipeline...")
    run_pipeline(test_video, "test_event")

    # 4. Verify proxy exists
    proxy_path = ARCHIVE_ROOT / "proxy" / "low_fps" / "test_event" / "_pipeline_test_part001.mp4"
    if proxy_path.exists():
        print(f"PASS: Proxy created — {proxy_path.stat().st_size // 1024}KB")
    else:
        print(f"FAIL: Proxy not found at {proxy_path}")
        sys.exit(1)

    # 5. Verify audio exists
    audio_path = ARCHIVE_ROOT / "audio" / "test_event" / "_pipeline_test_part001.wav"
    if audio_path.exists():
        print(f"PASS: Audio created — {audio_path.stat().st_size // 1024}KB")
    else:
        print(f"FAIL: Audio not found at {audio_path}")
        sys.exit(1)

    print("\n=== INGEST pipeline test PASSED ===")
    print("Check n8n for incoming webhook in test_event executions.")


if __name__ == "__main__":
    main()
