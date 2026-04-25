"""Test FEEDBACK stage: user description → delta → prompt suggestion."""
import sys, json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).parents[1]))


def main():
    print("=== FEEDBACK Stage Test ===")

    from agents.interface.app import app
    client = app.test_client()

    # 1. Feedback on existing segment (from archive writer test)
    r = client.post("/feedback", json={
        "segment_id": 1,
        "user_description": "fire eating performance with crowd cheering loudly"
    })
    assert r.status_code == 200, f"FAIL: POST /feedback returned {r.status_code}"
    d = json.loads(r.data)
    assert d.get("saved") is True, "FAIL: saved != True"
    assert "delta" in d, "FAIL: missing delta"
    assert "prompt_suggestion" in d, "FAIL: missing prompt_suggestion"
    print(f"PASS: Feedback saved — delta: {d['delta'][:80]}")
    print(f"      Suggestion: {d['prompt_suggestion'][:100]}")

    # 2. Feedback with no description returns 400
    r2 = client.post("/feedback", json={"segment_id": 1, "user_description": ""})
    assert r2.status_code == 400, f"FAIL: empty description should return 400, got {r2.status_code}"
    print("PASS: Empty description correctly rejected (400)")

    # 3. Feedback for non-existent segment returns 404
    r3 = client.post("/feedback", json={"segment_id": 99999, "user_description": "test"})
    assert r3.status_code == 404, f"FAIL: non-existent segment should return 404, got {r3.status_code}"
    print("PASS: Non-existent segment correctly returns 404")

    # 4. /analyze endpoint accepts payload and queues in background
    r4 = client.post("/analyze", json={
        "gcs_path":       "gs://magzimus-video-raw/Proxy_files/test_event/_pipeline_test_part001.mp4",
        "gcs_audio_path": "gs://magzimus-video-raw/Audio/test_event/_pipeline_test_part001.wav",
        "source_file":    "_pipeline_test.mp4",
        "event_type":     "test_event",
        "part_index":     1,
        "total_parts":    1,
        "duration_seconds": 35.0,
        "source_fps":     25,
        "environment":    "TEST",
    })
    assert r4.status_code == 200, f"FAIL: /analyze returned {r4.status_code}"
    d4 = json.loads(r4.data)
    assert d4.get("accepted") is True, "FAIL: /analyze accepted != True"
    print("PASS: /analyze accepted payload and queued analysis")

    print("\n=== FEEDBACK stage test PASSED ===")


if __name__ == "__main__":
    main()
