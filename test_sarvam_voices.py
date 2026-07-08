"""
Plays the same sentence through v2 and v3 so you can compare voice quality.
Run: python test_sarvam_voices.py
"""
import os, time, base64
import numpy as np
import sounddevice as sd
import requests
from dotenv import load_dotenv
load_dotenv()

SARVAM_KEY = os.getenv("SARVAM_API_KEY", "")
SR = 16000

def speak(text, model, speaker, language, extra={}):
    payload = {
        "text": text,
        "target_language_code": language,
        "speaker": speaker,
        "speech_sample_rate": SR,
        "model": model,
        "pace": 1.0,
        **extra
    }
    t0 = time.time()
    r = requests.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": SARVAM_KEY,
                 "Content-Type": "application/json"},
        json=payload, timeout=15,
    )
    elapsed = (time.time() - t0) * 1000
    r.raise_for_status()
    wav = base64.b64decode(r.json()["audios"][0])
    pcm = wav[44:] if wav[:4] == b"RIFF" else wav
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    print(f"  {model} ({speaker}): {elapsed:.0f}ms")
    sd.play(audio, SR)
    sd.wait()

sentences = [
    ("SIP cancel karne se aapka SIP permanently band ho jaata hai, dobara register karna padega.", "hi-IN"),
    ("Your SIP cancel request has been submitted, it will be processed in 3 working days.", "en-IN"),
]

for text, lang in sentences:
    print(f"\nText: \"{text[:60]}...\"")
    print("--- bulbul:v3 (pooja) ---")
    speak(text, "bulbul:v3", "pooja", lang, {"temperature": 0.6})
    time.sleep(0.3)
    print("--- bulbul:v2 (anushka) ---")
    speak(text, "bulbul:v2", "anushka", lang,
          {"pitch": 0.0, "loudness": 1.0, "enable_preprocessing": True})
    time.sleep(0.3)

print("\nDone — which sounded better?")