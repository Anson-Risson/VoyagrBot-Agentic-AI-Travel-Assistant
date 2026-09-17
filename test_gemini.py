import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

key = os.getenv("GOOGLE_API_KEY")

if key:
    try:
        client = genai.Client(api_key=key)
        response = client.models.generate_content(
            model="gemini-3-flash-preview", 
            contents="Explain how AI works in a few words"
        )
        print(response.text)
    except Exception as e:
        print(f"Error: {e}")
else:
    print("GOOGLE_API_KEY not found in .env")
