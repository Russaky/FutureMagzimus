"""Test ANALYSIS pipeline with the proxy/audio created by the ingest test."""
import os, sys, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).parents[1]))

ARCHIVE_ROOT = Path(os.getenv("ARCHIVE_ROOT", "/Volumes/Magzimus_2T/Magzimus_Video_Archive"))
GCS_BUCKET   = os.getenv("GCS_BUCKET", "magzimus-video-raw")

TEST_PAYLOAD = {
    "gcs_path":        f"gs://{GCS_BUCKET}/Proxy_files/test_event/_pipeline_test_part001.mp4",
    "gcs_audio_path":  f"gs://{GCS_BUCKET}/Audio/test_event/_pipeline_test_part001.wav",
    "source_file":     "_pipeline_test.mp4",
    "event_type":      "test_event",
    "part_index":      1,
    "total_parts":     1,
    "duration_seconds": 35.0,
    "source_fps":      25,
    "environment":     "TEST",
}


def main():
    print("=== ANALYSIS Pipeline Test ===")

    # Verify prerequisites from ingest test
    proxy_path = ARCHIVE_ROOT / "proxy" / "low_fps" / "test_event" / "_pipeline_test_part001.mp4"
    audio_path = ARCHIVE_ROOT / "audio" / "test_event" / "_pipeline_test_part001.wav"
    if not proxy_path.exists() or not audio_path.exists():
        print("FAIL: Run test_ingest_pipeline.py first — proxy/audio not found")
        sys.exit(1)

    from agents.analysis.pipeline import run_analysis
    print("Running analysis pipeline (Audio → Performance → Documentary → Critic)...")
    merged = run_analysis(TEST_PAYLOAD)

    # Verify structure
    assert "clip_meta" in merged, "FAIL: merged missing clip_meta"
    assert "segments"  in merged, "FAIL: merged missing segments"
    assert len(merged["segments"]) > 0, "FAIL: no segments returned"
    print(f"PASS: {len(merged['segments'])} segment(s) in merged output")

    # Verify merged JSON written locally
    merged_path = ARCHIVE_ROOT / "merged" / "test_event" / "_pipeline_test_part001_merged.json"
    if merged_path.exists():
        print(f"PASS: Merged JSON saved locally — {merged_path.stat().st_size} bytes")
    else:
        print(f"FAIL: Merged JSON not found at {merged_path}")
        sys.exit(1)

    # Verify GCS upload
    from agents.ingest.gcs_uploader import _get_client
    client = _get_client()
    bucket = client.bucket(GCS_BUCKET)
    blob   = bucket.blob(f"merged/test_event/_pipeline_test_part001_merged.json")
    if blob.exists():
        print(f"PASS: Merged JSON uploaded to GCS")
    else:
        print(f"FAIL: Merged JSON not found in GCS")
        sys.exit(1)

    # Print first segment summary
    seg = merged["segments"][0]
    print(f"\nFirst segment: {seg.get('tc_start')} → {seg.get('tc_end')}")
    print(f"  content_tags:  {seg.get('content_tags', [])}")
    print(f"  context_tags:  {seg.get('context_tags', [])}")
    print(f"  scores_final:  {seg.get('scores_final')}")
    print(f"  performance:   {seg.get('performance_level')}")
    print(f"  crowd:         {seg.get('crowd_response')}")

    print("\n=== ANALYSIS pipeline test PASSED ===")


if __name__ == "__main__":
    main()
