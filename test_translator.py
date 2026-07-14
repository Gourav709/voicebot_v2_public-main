import os
from dotenv import load_dotenv

load_dotenv()

from src.providers.llm_groq import GroqLLM
llm = GroqLLM(
    enabled=True,
    api_key=os.getenv("GROQ_API_KEY"),
    model=os.getenv("GROQ_MODEL"),
    temperature=0,
    max_tokens=300,
    timeout=30,
)

text = input("Enter any language: ")

english = llm.translate_to_english(text)

print("\nEnglish Translation:")
print(english)

target_language = input("\nTarget language code (hi-IN, ta-IN, te-IN, gu-IN): ")

translated = llm.translate_from_english(
    english,
    target_language
)

print("\nTranslated Back:")
print(translated)