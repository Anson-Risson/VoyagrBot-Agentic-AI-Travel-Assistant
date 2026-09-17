import google.generativeai as genai
import os
from dotenv import load_dotenv

load_dotenv(override=True)
api_key = os.getenv("GOOGLE_API_KEY")
model_output = "gemini_models.txt"

if not api_key:
    with open(model_output, "w") as f:
        f.write("GOOGLE_API_KEY not found in .env")
else:
    genai.configure(api_key=api_key)
    try:
        with open(model_output, "w") as f:
            f.write("Available models:\n")
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    f.write(f"{m.name}\n")
        print(f"Models list saved to {model_output}")
    except Exception as e:
        with open(model_output, "w") as f:
            f.write(f"Error: {e}")
        print(f"Error list models: {e}")
