"""Test 4: Gemini API via Google AI Studio API key."""
import os, sys
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("FAIL: GEMINI_API_KEY not set in .env")
        sys.exit(1)

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        resp = client.models.generate_content(
            model="gemini-2.0-flash",
            contents="Reply with only the word: pong"
        )
        text = resp.text.strip().lower()
        print(f"PASS: Gemini OK — model=gemini-2.0-flash response='{text}'")
    except ImportError:
        print("FAIL: google-genai not installed — run: pip3 install google-genai")
        sys.exit(1)
    except Exception as e:
        print(f"FAIL: Gemini error — {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
