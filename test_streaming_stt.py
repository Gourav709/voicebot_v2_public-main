"""
Standalone streaming STT test.
Run: python test_streaming_stt.py  |  Stop: Ctrl+C

Measures post-speech lag — time from when you stop speaking
until transcript is ready. That's the latency streaming saves.
"""
import os, sys, time, json, threading
import numpy as np
import sounddevice as sd
import websocket
from dotenv import load_dotenv
load_dotenv()

API_KEY  = os.getenv("DEEPGRAM_API_KEY", "")
SR       = 16000
FRAME_MS = 20
FRAME_LEN = int(SR * FRAME_MS / 1000)

if not API_KEY:
    print("ERROR: DEEPGRAM_API_KEY not set in .env")
    sys.exit(1)

WS_URL = (
    "wss://api.deepgram.com/v1/listen"
    "?model=nova-2-general"
    "&language=hi"
    "&punctuate=true"
    "&smart_format=true"
    "&encoding=linear16"
    f"&sample_rate={SR}"
    "&channels=1"
    "&interim_results=true"
    "&endpointing=300"
    "&utterance_end_ms=1000"
    "&vad_events=true"
)

# ── Shared state (all accessed from WebSocket thread) ─────────────────────────
state = {
    "ws":             None,
    "running":        True,
    "turn_count":     0,
    "speech_start":   None,
    "speech_end":     None,
    "last_final_t":   None,
    "last_text":      "",
    "accumulated":    [],    # list of Final transcripts — joined on speech_final
}

# ── Handlers ──────────────────────────────────────────────────────────────────
def on_open(ws):
    print("✓ Connected to Deepgram WebSocket")
    print("─" * 60)
    print("Speak — partials appear live. Post-speech lag = STT latency.\n")

def on_message(ws, message):
    try:
        data     = json.loads(message)
        msg_type = data.get("type", "")

        if msg_type == "SpeechStarted":
            # If a previous utterance was in progress, mark its end
            if state["speech_start"] and not state["speech_end"]:
                state["speech_end"] = time.time()
            # Only set speech_start if not already in an utterance
            if not state["speech_start"]:
                state["speech_start"] = time.time()
            state["speech_end"] = None
            print("  \033[2m[speech started]\033[0m")

        elif msg_type == "Results":
            ch          = data.get("channel", {})
            alt         = ch.get("alternatives", [{}])[0]
            transcript  = alt.get("transcript", "").strip()
            is_final    = data.get("is_final", False)
            speech_final = data.get("speech_final", False)

            if not transcript:
                return

            state["last_text"] = transcript

            if speech_final:
                now    = time.time()
                s_end  = state["speech_end"] or state["last_final_t"] or (now - 0.3)
                lag_ms = (now - s_end) * 1000
                dur_ms = (s_end - state["speech_start"]) * 1000 if state["speech_start"] else 0
                state["turn_count"] += 1
                # Build full utterance from accumulated Finals + final fragment
                full_utterance = " ".join(state["accumulated"] + ([transcript] if transcript not in state["accumulated"] else [])).strip()
                print(f"\r  \033[92mSpeech Final:\033[0m {transcript}          ")
                print(f"  \033[2m  speech duration : {dur_ms:.0f}ms\033[0m")
                print(f"  \033[1m  post-speech lag : {lag_ms:.0f}ms  ← STT latency\033[0m")
                print(f"  \033[32m  → LLM would receive: \"{full_utterance}\"\033[0m\n")
                state["speech_start"] = None
                state["speech_end"]   = None
                state["last_final_t"] = None
                state["last_text"]    = ""
                state["accumulated"]  = []

            elif is_final:
                state["last_final_t"] = time.time()
                state["accumulated"].append(transcript)
                print(f"\r  \033[94mFinal   :\033[0m {transcript}          ")

            else:
                print(f"\r  \033[2mPartial :\033[0m {transcript}          ", end="", flush=True)

        elif msg_type == "UtteranceEnd":
            if not state["last_text"] and not state["accumulated"]:
                return   # duplicate — speech_final already handled this utterance
            # Build full utterance from accumulated Finals
            full_utt = " ".join(state["accumulated"]).strip() or state["last_text"]
            txt      = full_utt
            now    = time.time()
            s_end  = state["speech_end"] or state["last_final_t"] or (now - 0.3)
            lag_ms = (now - s_end) * 1000
            dur_ms = (s_end - state["speech_start"]) * 1000 if state["speech_start"] else 0
            state["turn_count"] += 1
            print(f"\r  \033[93mUtteranceEnd:\033[0m {txt}          ")
            print(f"  \033[2m  speech duration : {dur_ms:.0f}ms\033[0m")
            print(f"  \033[1m  post-speech lag : {lag_ms:.0f}ms  ← STT latency (via UtteranceEnd)\033[0m")
            print(f"  \033[32m  → LLM would receive: \"{txt}\"\033[0m\n")
            state["speech_start"] = None
            state["speech_end"]   = None
            state["last_final_t"] = None
            state["last_text"]    = ""
            state["accumulated"]  = []

        elif msg_type == "Metadata":
            print(f"  \033[2mSession: {data.get('duration', 0):.1f}s audio processed\033[0m")

        elif msg_type == "Error":
            print(f"  \033[91mDeepgram error: {data}\033[0m")

    except Exception as e:
        import traceback
        print(f"\nMessage error: {e}")
        traceback.print_exc()

def on_error(ws, error):
    # Suppress the normal close-collision error on Ctrl+C
    err = str(error)
    if "opcode=8" in err or "fin=1" in err:
        return
    print(f"\n\033[91mWebSocket error: {error}\033[0m")

def on_close(ws, code, msg):
    print(f"\n\033[2mClosed: {code}\033[0m")

def audio_callback(indata, frames, time_info, status):
    if not state["running"] or state["ws"] is None:
        return
    pcm16 = (np.clip(indata[:, 0], -1, 1) * 32767).astype(np.int16).tobytes()
    try:
        state["ws"].send(pcm16, websocket.ABNF.OPCODE_BINARY)
    except Exception:
        pass

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ws = websocket.WebSocketApp(
        WS_URL,
        header={"Authorization": f"Token {API_KEY}"},
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
    )
    state["ws"] = ws

    threading.Thread(target=ws.run_forever,
                     kwargs={"ping_interval": 10},
                     daemon=True).start()
    time.sleep(0.8)

    print(f"Opening mic at {SR}Hz...")
    try:
        with sd.InputStream(samplerate=SR, channels=1, dtype="float32",
                            blocksize=FRAME_LEN, callback=audio_callback):
            while state["running"]:
                time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nStopping...")
        state["running"] = False
        try:
            ws.send(json.dumps({"type": "CloseStream"}))
            time.sleep(0.5)
        except Exception:
            pass
        ws.close()
        print(f"Done — {state['turn_count']} utterance(s) detected.")

if __name__ == "__main__":
    try:
        import websocket
    except ImportError:
        print("Run: pip install websocket-client")
        sys.exit(1)
    main()