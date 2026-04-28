from dotenv import load_dotenv
load_dotenv()
import os
import google.generativeai as genai
api_key = os.environ.get("GEMINI_API_KEY")
genai.configure(api_key=api_key)
print("Available models:")
for m in genai.list_models():
    print(m.name)
