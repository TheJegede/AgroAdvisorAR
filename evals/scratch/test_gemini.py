import os
from pathlib import Path
from dotenv import load_dotenv

# Load the backend .env explicitly — this scratch script runs from evals/scratch
# where a bare load_dotenv() would not find it.
load_dotenv(Path(__file__).resolve().parents[2] / "backend" / ".env")

from langchain_google_genai import ChatGoogleGenerativeAI

print("GOOGLE_API_KEY present:", bool(os.environ.get("GOOGLE_API_KEY")))

try:
    print("Testing gemini-2.5-flash...")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")
    resp = llm.invoke("Hello, say 'ready'")
    print("SUCCESS:", resp.content)
except Exception as e:
    print("FAILED gemini-2.5-flash:", e)

try:
    print("\nTesting gemini-2.5-flash-lite...")
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash-lite")
    resp = llm.invoke("Hello, say 'ready'")
    print("SUCCESS:", resp.content)
except Exception as e:
    print("FAILED gemini-2.5-flash-lite:", e)
