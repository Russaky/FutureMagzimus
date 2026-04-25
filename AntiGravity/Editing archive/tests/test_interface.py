"""Test Flask interface — start app, hit / and /export."""
import os, sys, json, threading, time
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parents[1] / ".env")
sys.path.insert(0, str(Path(__file__).parents[1]))

DB_PATH = Path(os.getenv("ARCHIVE_DB", "/Volumes/Magzimus_2T/Magzimus_Video_Archive/archive.db"))


def main():
    print("=== INTERFACE Test ===")

    # Prerequisite: DB must exist (run test_archive_writer.py first)
    if not DB_PATH.exists():
        print("FAIL: archive.db not found — run test_archive_writer.py first")
        sys.exit(1)

    from agents.interface.app import app
    app.config["TESTING"] = True
    client = app.test_client()

    # 1. Test index page loads
    resp = client.get("/")
    assert resp.status_code == 200, f"FAIL: GET / returned {resp.status_code}"
    body = resp.data.decode()
    assert "Magzimus Archive" in body, "FAIL: index page missing title"
    assert "result(s)" in body, "FAIL: index page missing results count"
    print("PASS: GET / — index page loads")

    # 2. Test filter by content_tag
    resp = client.get("/?content_tag=fire_eating")
    assert resp.status_code == 200, f"FAIL: GET /?content_tag=fire_eating returned {resp.status_code}"
    print("PASS: GET /?content_tag=fire_eating — filtered query works")

    # 3. Test export with no segment_ids
    resp = client.post("/export", json={"segment_ids": []})
    assert resp.status_code == 400, f"FAIL: empty export should return 400, got {resp.status_code}"
    print("PASS: POST /export with empty list returns 400")

    # 4. Test export with a valid segment (from archive test)
    import sqlite3
    conn = sqlite3.connect(str(DB_PATH))
    row = conn.execute("SELECT id FROM segments LIMIT 1").fetchone()
    conn.close()
    if row:
        resp = client.post("/export", json={"segment_ids": [str(row[0])]})
        assert resp.status_code == 200, f"FAIL: /export returned {resp.status_code}"
        data = resp.get_json()
        print(f"PASS: POST /export — {data.get('message', data)}")
    else:
        print("SKIP: No segments in DB for export test")

    print("\n=== INTERFACE test PASSED ===")


if __name__ == "__main__":
    main()
