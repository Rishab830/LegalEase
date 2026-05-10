import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

print(f"Key from .env: {api_key[:5]}...{api_key[-4:] if api_key else 'None'}")

if not api_key:
    print("❌ FAILED: Could not find GEMINI_API_KEY in .env")
else:
    try:
        client = genai.Client(api_key=api_key)
        # Use the correct model name
        response = client.models.generate_content(
            model='gemini-2.5-flash', 
            contents="Say 'Environment is ready' if you can read this."
        )
        print(f"✅ SUCCESS: {response.text.strip()}")
    except Exception as e:
        print(f"❌ API ERROR: {e}")
