"""Debug v3: google-genai SDK with Credentials.from_service_account_file."""
import os, sys, json
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
with open(creds_path) as f:
    sa = json.load(f)
project_id = sa.get("project_id")
print(f"project_id : {project_id}")
print(f"client_email: {sa.get('client_email')}")
print()

from google.genai import Client
from google.auth.service_account import Credentials

creds = Credentials.from_service_account_file(
    creds_path,
    scopes=["https://www.googleapis.com/auth/cloud-platform"]
)

locations = ["us-central1", "global", "europe-west4", "me-west1"]
models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-1.5-flash"]

for location in locations:
    for model in models:
        try:
            client = Client(
                vertexai=True,
                project=project_id,
                location=location,
                credentials=creds
            )
            resp = client.models.generate_content(
                model=model,
                contents="Reply with only the word: pong"
            )
            print(f"SUCCESS: {model} @ {location} => {resp.text.strip()}")
            sys.exit(0)
        except Exception as e:
            print(f"FAIL: {model} @ {location} => {str(e)[:120]}")
