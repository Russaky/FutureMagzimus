"""Test 1: GCS read/write connectivity."""
import os, sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def main():
    try:
        from google.cloud import storage
    except ImportError:
        print("FAIL: google-cloud-storage not installed")
        sys.exit(1)

    creds = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
    bucket_name = os.getenv("GCS_BUCKET")

    if not creds or not os.path.exists(creds):
        print(f"FAIL: GOOGLE_APPLICATION_CREDENTIALS missing or file not found: {creds}")
        sys.exit(1)

    try:
        client = storage.Client.from_service_account_json(creds)
        bucket = client.bucket(bucket_name)

        # Write test
        blob = bucket.blob("_connection_test/ping.txt")
        blob.upload_from_string("ok")

        # Read test
        data = blob.download_as_text()
        assert data == "ok", f"Read mismatch: {data}"

        # Cleanup
        blob.delete()

        print(f"PASS: GCS read/write OK — bucket={bucket_name}")
    except Exception as e:
        print(f"FAIL: GCS error — {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
