"""
Quick test — compares language=multi vs language=hi transcription quality.
Run: python test_hindi_debug.py
"""
import os, requests, numpy as np, sounddevice as sd
from dotenv import load_dotenv
load_dotenv()

SR = 16000
api_key = os.getenv("DEEPGRAM_API_KEY", "")

def record(label):
    print(f"\n🎙  {label} — speak for 4 seconds...")
    audio = sd.rec(int(4 * SR), samplerate=SR, channels=1, dtype='int16')
    sd.wait()
    return audio.tobytes()

def transcribe(pcm, language):
    r = requests.post(
        "https://api.deepgram.com/v1/listen",
        params={"model": "nova-2-general", "language": language,
                "punctuate": "true", "encoding": "linear16",
                "sample_rate": SR, "channels": 1},
        headers={"Authorization": f"Token {api_key}", "Content-Type": "audio/raw"},
        data=pcm, timeout=15,
    )
    ch = r.json().get("results", {}).get("channels", [{}])[0]
    return ch.get("alternatives", [{}])[0].get("transcript", "")

# Test with same sentence sent to both
pcm = record("Speak a full Hindi sentence (same sentence for both tests)")

print(f"\nlanguage=multi : '{transcribe(pcm, 'multi')}'")
print(f"language=hi    : '{transcribe(pcm, 'hi')}'")
print(f"language=en-IN : '{transcribe(pcm, 'en-IN')}'")