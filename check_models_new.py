from google import genai
import os
from dotenv import load_dotenv

load_dotenv(override=True)
api_key = os.getenv("GOOGLE_API_KEY")

if not api_key:
    print("GOOGLE_API_KEY not found")
else:
    client = genai.Client(api_key=api_key)
    try:
        print("Available models:")
        for m in client.models.list():
            print(m.name)
    except Exception as e:
        print(f"Error: {e}")
