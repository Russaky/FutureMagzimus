"""Test 3: n8n webhook endpoint reachable.

NOTE: n8n test-mode webhooks require clicking 'Execute workflow' on the canvas
before each call. This test instead verifies the PROD webhook URL is reachable
(returns anything other than a network error), which confirms routing is live.
For full end-to-end webhook testing, use scripts/manual_webhook_test.sh.
"""
import os, sys, requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def main():
    # Prefer PROD URL for connectivity check — it's always registered
    webhook_url = os.getenv("N8N_WEBHOOK_PROD") or os.getenv("N8N_WEBHOOK_TEST")

    if not webhook_url:
        print("FAIL: N8N_WEBHOOK_PROD not set")
        sys.exit(1)

    try:
        # HEAD request — just verify the host is reachable, don't trigger execution
        resp = requests.head(webhook_url, timeout=10, allow_redirects=True)
        # n8n returns 200, 404, or 405 — all mean the server responded
        if resp.status_code < 500:
            print(f"PASS: n8n webhook host reachable — HTTP {resp.status_code} (server up)")
        else:
            print(f"FAIL: n8n server error — HTTP {resp.status_code}")
            sys.exit(1)
    except requests.exceptions.ConnectionError as e:
        print(f"FAIL: n8n unreachable — {e}")
        sys.exit(1)
    except Exception as e:
        print(f"FAIL: webhook error — {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
