"""
Standalone streaming LLM → TTS pipeline test.
Completely independent of the bot.

Tests:
  1. Groq streaming tokens arrive correctly
  2. Sentence splitter fires at correct boundaries (Hindi + English + mixed)
  3. Sarvam TTS called per sentence and audio plays in real time
  4. Measures: time to first audio vs current batch approach

Run: python test_streaming_llm_tts.py
"""
import os, sys, time, re, queue, threading
import requests
import sounddevice as sd
import numpy as np
from dotenv import load_dotenv
load_dotenv()

GROQ_KEY   = os.getenv("GROQ_API_KEY", "")
SARVAM_KEY = os.getenv("SARVAM_API_KEY", "")
GROQ_MODEL = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")
SR         = 16000

if not GROQ_KEY:
    print("ERROR: GROQ_API_KEY not set in .env"); sys.exit(1)
if not SARVAM_KEY:
    print("ERROR: SARVAM_API_KEY not set in .env"); sys.exit(1)

# ── Sentence splitter ─────────────────────────────────────────────────────────
# Splits on: . ! ? । (Hindi full stop) followed by space or end
# Keeps English terms like "MF Reports", "SIP" intact
SPLIT_RE = re.compile(r'(?<=[.!?।])\s+')

def split_sentences(text: str) -> list[str]:
    parts = SPLIT_RE.split(text.strip())
    return [p.strip() for p in parts if p.strip()]

# ── Groq streaming ────────────────────────────────────────────────────────────
def stream_groq(prompt: str, language: str = "en-IN"):
    """
    Yields text tokens from Groq as they arrive.
    Uses stream=true — Server-Sent Events (SSE).
    """
    lang_instruction = (
        "Reply in Hindi using Devanagari script. Keep English terms like SIP, OTP in Roman."
        if language == "hi-IN" else
        "Reply in natural Indian English."
    )
    r = requests.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {GROQ_KEY}",
                 "Content-Type": "application/json"},
        json={
            "model":       GROQ_MODEL,
            "messages":    [{"role": "user", "content": f"{lang_instruction}\n\n{prompt}"}],
            "temperature": 0.3,
            "max_tokens":  60,
            "stream":      True,
            # NOTE: no response_format=json_object — plain text for TTS
        },
        stream=True,
        timeout=30,
    )
    if not r.ok:
        print(f"  [Sarvam] Error {r.status_code}: {r.text}")
    r.raise_for_status()
    for line in r.iter_lines():
        if not line:
            continue
        line = line.decode("utf-8")
        if line.startswith("data: "):
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                import json
                chunk = json.loads(data)
                delta = chunk["choices"][0]["delta"].get("content", "")
                if delta:
                    yield delta
            except Exception:
                pass

# ── Sarvam TTS ────────────────────────────────────────────────────────────────
def tts_synthesize(text: str, language: str = "en-IN") -> bytes:
    """Call Sarvam and return raw PCM16 bytes."""
    import base64
    print(f"  [Sarvam] calling API for: \"{text[:50]}\" ({language})")
    r = requests.post(
        "https://api.sarvam.ai/text-to-speech",
        headers={"api-subscription-key": SARVAM_KEY,
                 "Content-Type": "application/json"},
        json={
            "text":                 text,
            "target_language_code": language,
            "speaker":              "pooja",
            "speech_sample_rate":   SR,
            "model":                "bulbul:v3",
            "pace":                 1.0,
            "temperature":          0.6,   # required for bulbul:v3
        },
        timeout=15,
    )
    if not r.ok:
        print(f"  [Sarvam] Error {r.status_code}: {r.text}")
    r.raise_for_status()
    result = r.json()
    audios = result.get("audios", [])
    if not audios:
        return b""
    wav = base64.b64decode(audios[0])
    return wav[44:] if wav[:4] == b"RIFF" else wav  # strip WAV header

# ── Audio playback ─────────────────────────────────────────────────────────────
def play_pcm(pcm: bytes):
    audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    print(f"  [play_pcm] playing {len(audio)} samples ({len(audio)/SR:.2f}s)")
    sd.play(audio, SR)
    sd.wait()
    print(f"  [play_pcm] done")

# ── Pipeline ──────────────────────────────────────────────────────────────────
def run_streaming_pipeline(prompt: str, language: str = "en-IN"):
    """
    Full streaming pipeline:
    1. Stream tokens from Groq
    2. Detect sentence boundaries
    3. Fire Sarvam TTS per sentence in background thread
    4. Play audio as each sentence arrives
    """
    print(f"\n{'─'*60}")
    print(f"Prompt: {prompt}")
    print(f"{'─'*60}")

    audio_queue  = queue.Queue()
    t_start      = time.time()
    t_first_audio = None
    full_text    = ""
    buffer       = ""
    sentences    = []

    def tts_worker():
        """Background: converts sentence text → audio and queues it."""
        nonlocal t_first_audio
        print("  [TTS worker started]")
        while True:
            item = audio_queue.get()
            if item is None:
                print("  [TTS worker received stop signal]")
                break
            sentence, idx = item
            print(f"  [TTS worker] synthesising sentence {idx}: \"{sentence[:60]}\"")
            t_tts = time.time()
            try:
                pcm = tts_synthesize(sentence, language)
                t_done = time.time()
                print(f"  [TTS worker] got {len(pcm)} bytes in {(t_done-t_tts)*1000:.0f}ms")
                if not pcm:
                    print(f"  [TTS worker] WARNING: empty audio for sentence {idx}")
                    audio_queue.task_done()
                    continue
                if t_first_audio is None:
                    t_first_audio = t_done
                    print(f"  ⚡ First audio ready: {(t_done - t_start)*1000:.0f}ms from LLM start")
                print(f"  🔊 [{idx}] TTS in {(t_done-t_tts)*1000:.0f}ms: \"{sentence[:50]}\"")
                print(f"  [TTS worker] calling play_pcm...")
                play_pcm(pcm)
                print(f"  [TTS worker] play_pcm done")
            except Exception as e:
                import traceback
                print(f"  ✗ TTS error on sentence {idx}: {e}")
                traceback.print_exc()
            audio_queue.task_done()

    worker = threading.Thread(target=tts_worker, daemon=True)
    worker.start()

    # Stream tokens and split into sentences
    t_first_token = None
    sent_idx      = 0
    print("  Streaming tokens: ", end="", flush=True)

    for token in stream_groq(prompt, language):
        if t_first_token is None:
            t_first_token = time.time()
            print(f"\n  ⚡ First token: {(t_first_token - t_start)*1000:.0f}ms")
            print("  Tokens: ", end="", flush=True)

        print(token, end="", flush=True)
        buffer    += token
        full_text += token

        # Check for sentence boundaries
        parts = SPLIT_RE.split(buffer)
        if len(parts) > 1:
            for sentence in parts[:-1]:
                sentence = sentence.strip()
                if sentence:
                    sent_idx += 1
                    t_detected = time.time()
                    print(f"\n  ✓ Sentence {sent_idx} at {(t_detected-t_start)*1000:.0f}ms → TTS queued")
                    print("  Tokens: ", end="", flush=True)
                    audio_queue.put((sentence, sent_idx))
                    sentences.append(sentence)
            buffer = parts[-1]  # remainder after last boundary

    # Fire any remaining buffer as final sentence
    if buffer.strip():
        sent_idx += 1
        print(f"\n  ✓ Sentence {sent_idx} (final) → TTS queued")
        audio_queue.put((buffer.strip(), sent_idx))
        sentences.append(buffer.strip())

    t_llm_done = time.time()
    print(f"\n  ⚡ LLM complete: {(t_llm_done - t_start)*1000:.0f}ms  ({sent_idx} sentences)")

    # Wait for all TTS + playback to finish
    audio_queue.put(None)
    worker.join()

    t_end = time.time()
    print(f"\n  Total time : {(t_end - t_start)*1000:.0f}ms")
    print(f"  Full text  : \"{full_text.strip()}\"")

# ── Sentence splitter unit test ───────────────────────────────────────────────
def test_sentence_splitter():
    print("=" * 60)
    print("TEST 1: Sentence splitter")
    print("=" * 60)
    cases = [
        "SIP cancel karne se permanently band ho jaata hai. Dobara register karna padega.",
        "SIP pause में आप SIP रोक सकते हैं। Cancel करने से पूरी तरह बंद हो जाता है।",
        "No penalty for pausing! You can restart anytime. But cancel is permanent.",
        "MF Reports mein jaao. Systematic Plans section kholo. Wahan se request daalo.",
    ]
    for text in cases:
        sentences = split_sentences(text)
        print(f"  Input : {text[:60]}...")
        for i, s in enumerate(sentences):
            print(f"    [{i+1}] {s}")
        print()

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    test_sentence_splitter()

    print("=" * 60)
    print("TEST 2: English — streaming LLM → TTS pipeline")
    print("=" * 60)
    run_streaming_pipeline(
        prompt="In max 15 words total, explain what SIP cancel means.",
        language="en-IN",
    )

    time.sleep(0.5)

    print("\n" + "=" * 60)
    print("TEST 3: Hindi — streaming LLM → TTS pipeline")
    print("=" * 60)
    run_streaming_pipeline(
        prompt="15 words ya kam mein batao: SIP cancel karne se kya hota hai?",
        language="hi-IN",
    )

    print("\n✓ All tests complete.")


# ── Bonus: Sarvam model latency comparison ────────────────────────────────────
def test_sarvam_latency():
    import base64
    print("\n" + "=" * 60)
    print("TEST 4: Sarvam model latency comparison")
    print("=" * 60)
    test_text = "SIP cancel karne se aapka SIP permanently band ho jaata hai."

    for model, speaker, extra in [
        ("bulbul:v3", "pooja",   {"temperature": 0.6}),
        ("bulbul:v2", "anushka", {"pitch": 0.0, "loudness": 1.0, "enable_preprocessing": True}),
    ]:
        payload = {
            "text":                 test_text,
            "target_language_code": "hi-IN",
            "speaker":              speaker,
            "speech_sample_rate":   16000,
            "model":                model,
            "pace":                 1.0,
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
        if r.ok:
            result  = r.json()
            wav     = base64.b64decode(result["audios"][0])
            pcm     = wav[44:] if wav[:4] == b"RIFF" else wav
            dur_sec = len(pcm) / (16000 * 2)
            print(f"  {model:12} ({speaker:8}): {elapsed:.0f}ms → {dur_sec:.1f}s audio  (RTF: {elapsed/1000/dur_sec:.2f}x)")
        else:
            print(f"  {model:12}: ERROR {r.status_code} — {r.text[:100]}")

if __name__ == "__main__" or True:
    test_sarvam_latency()