"""
Run: python test_deepgram_multilingual.py
Tests correct Deepgram multilingual param combos with real mic audio.
"""
import os, sys, time
import numpy as np
import sounddevice as sd
import requests
from dotenv import load_dotenv
load_dotenv()

api_key = os.getenv("DEEPGRAM_API_KEY", "")
if not api_key:
    print("ERROR: DEEPGRAM_API_KEY not set"); sys.exit(1)

SAMPLE_RATE = 16000
DURATION = 4  # seconds

def record(duration=4):
    print(f"  🎙  Recording {duration}s — speak now...")
    audio = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE,
                   channels=1, dtype='int16')
    sd.wait()
    return audio.tobytes()

url = "https://api.deepgram.com/v1/listen"
headers = {"Authorization": f"Token {api_key}", "Content-Type": "audio/raw"}
base = {"model": "nova-2", "punctuate": "true", "smart_format": "true",
        "encoding": "linear16", "sample_rate": SAMPLE_RATE, "channels": 1}

print("=== Test A: language=multi only (NO detect_language) — correct for multilingual ===")
pcm = record()
params = {**base, "language": "multi"}
r = requests.post(url, params=params, headers=headers, data=pcm, timeout=15)
j = r.json()
ch = j.get("results", {}).get("channels", [{}])[0]
print(f"  transcript: '{ch.get('alternatives',[{}])[0].get('transcript','')}'")
print(f"  detected_language field: '{ch.get('detected_language', 'NOT PRESENT')}'")
print()

print("=== Test B: detect_language=true + language=en (separate feature, for fixed-language detection) ===")
pcm = record()
params = {**base, "language": "en", "detect_language": "true"}
r = requests.post(url, params=params, headers=headers, data=pcm, timeout=15)
j = r.json()
ch = j.get("results", {}).get("channels", [{}])[0]
print(f"  transcript: '{ch.get('alternatives',[{}])[0].get('transcript','')}'")
print(f"  detected_language field: '{ch.get('detected_language', 'NOT PRESENT')}'")
print()

print("=== Test C: language=hi only (pure Hindi) ===")
pcm = record()
params = {**base, "language": "hi"}
r = requests.post(url, params=params, headers=headers, data=pcm, timeout=15)
j = r.json()
ch = j.get("results", {}).get("channels", [{}])[0]
print(f"  transcript: '{ch.get('alternatives',[{}])[0].get('transcript','')}'")
print(f"  detected_language field: '{ch.get('detected_language', 'NOT PRESENT')}'")