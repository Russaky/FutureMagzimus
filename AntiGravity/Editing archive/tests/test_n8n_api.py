"""Test 2: n8n API key + workflow list."""
import os, sys, requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def main():
    base_url = os.getenv("N8N_BASE_URL")
    api_key = os.getenv("N8N_API_KEY")

    if not base_url or not api_key:
        print("FAIL: N8N_BASE_URL or N8N_API_KEY not set")
        sys.exit(1)

    try:
        api_key.encode("latin-1")
    except UnicodeEncodeError:
        print("FAIL: N8N_API_KEY contains non-ASCII characters — paste the real key into .env")
        sys.exit(1)

    try:
        resp = requests.get(
            f"{base_url}/api/v1/workflows",
            headers={"X-N8N-API-KEY": api_key},
            timeout=10
        )
        if resp.status_code == 200:
            workflows = resp.json().get("data", [])
            print(f"PASS: n8n API OK — {len(workflows)} workflow(s) found")
        else:
            print(f"FAIL: n8n API returned HTTP {resp.status_code} — {resp.text[:200]}")
            sys.exit(1)
    except Exception as e:
        print(f"FAIL: n8n API error — {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
