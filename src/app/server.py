"""
WebSocket server for browser-based voice bot frontend.

Run: python run_server.py
Then open the ngrok URL in a browser.

Flow:
  Browser mic → WebSocket (binary PCM16 frames) → bot pipeline
  Bot audio    → WebSocket (binary PCM16)        → browser speaker
  Transcripts  → WebSocket (JSON events)         → browser UI
"""
import asyncio
import json
import os
import threading
import queue
import time
import numpy as np
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# Serve frontend static files
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

@app.get("/")
async def index():
    return FileResponse("frontend/index.html")


# ── Bot session per WebSocket connection ──────────────────────────────────────

class BotSession:
    """
    Wraps the existing bot pipeline for a single browser connection.
    Audio comes in as 16kHz PCM16 frames from the browser.
    """

    def __init__(self, websocket: WebSocket):
        self.ws          = websocket
        self.audio_queue = queue.Queue()   # incoming PCM16 frames from browser
        self.stopped     = threading.Event()
        self._loop       = asyncio.get_event_loop()

    async def send_event(self, event_type: str, data: dict):
        """Send a JSON event to the browser UI."""
        try:
            await self.ws.send_text(json.dumps({"type": event_type, **data}))
        except Exception:
            pass

    async def send_audio(self, pcm16: bytes):
        """Stream PCM16 audio bytes to browser."""
        try:
            await self.ws.send_bytes(pcm16)
        except Exception:
            pass

    def send_event_sync(self, event_type: str, data: dict):
        """Thread-safe version — called from bot worker thread."""
        asyncio.run_coroutine_threadsafe(
            self.send_event(event_type, data), self._loop
        )

    def send_audio_sync(self, pcm16: bytes):
        """Thread-safe version — called from bot worker thread."""
        asyncio.run_coroutine_threadsafe(
            self.send_audio(pcm16), self._loop
        )

    def run_bot(self):
        """Run bot pipeline in a background thread."""
        from src.app.main import load_config, initialize_components as build_components
        from src.core.orchestrator import OrchestratorV2

        config = load_config()

        # Override audio with browser WebSocket audio
        config["lookup_val"] = ""  # no customer lookup for web demo

        components = build_components(config)

        # Replace AudioIO with our WebSocket-backed version
        ws_audio = WebSocketAudioIO(
            session=self,
            sample_rate=config["sample_rate"],
            buffer_size=config.get("buffer_size", 1024),
        )
        components["audio"] = ws_audio

        # Patch TTS to also send audio to browser
        original_tts = components["tts"]
        components["tts"] = BrowserTTS(original_tts, self)

        bot = OrchestratorV2(
            audio=components["audio"],
            stt=components["stt"],
            llm=components["llm"],
            tts=components["tts"],
            faq_store=components["faq_store"],
            system_prompt_path=components["system_prompt_path"],
            llm_json_instructions_path=components["llm_json_instructions_path"],
            customer_context=components["customer_context"],
            logger=components["logger"],
            filler_manager=components.get("filler_manager"),
            greeting_prompt_path=components.get("greeting_prompt_path", "./config/prompts/greeting.txt"),
            llm_max_words=components.get("llm_max_words", 50),
            llm_context_turns=components.get("llm_context_turns", 5),
            summarise_every=components.get("llm_summarise_every", 3),
            silence_timeout_sec=components.get("silence_timeout_sec", 8),
            silence_max_prompts=components.get("silence_max_prompts", 2),
            llm_tts_streaming=components.get("llm_tts_streaming", False),
        )

        self.send_event_sync("status", {"msg": "Bot ready"})

        try:
            bot.run_loop()
        except Exception as e:
            self.send_event_sync("error", {"msg": str(e)})
        finally:
            self.stopped.set()


class WebSocketAudioIO:
    """
    Drop-in replacement for AudioIO that reads audio from browser WebSocket
    and writes audio back to it.
    """

    def __init__(self, session: BotSession, sample_rate: int = 16000,
                 buffer_size: int = 1024):
        self.session     = session
        self.sample_rate = sample_rate
        self.buffer_size = buffer_size
        self._play_lock  = threading.Lock()
        self._stats      = {"recordings": 0, "barge_ins": 0,
                            "denoised": 0, "total_audio_sec": 0.0}

    def record_utterance(self):
        """
        Collect PCM16 frames from the browser until silence.
        In streaming STT mode this is not called — stream_to_stt is used instead.
        """
        collected  = bytearray()
        silence_ms = 0
        MAX_SILENCE = 1200
        MAX_SEC     = 20

        deadline = time.time() + MAX_SEC
        while time.time() < deadline:
            try:
                frame = self.session.audio_queue.get(timeout=0.1)
                if frame is None:
                    break
                collected.extend(frame)
                silence_ms = 0
            except queue.Empty:
                silence_ms += 100
                if silence_ms >= MAX_SILENCE and len(collected) > 0:
                    break

        self._stats["recordings"] += 1
        return bytes(collected), self.sample_rate

    def stream_to_stt(self, streaming_stt, stop_event, muted=None):
        """Forward browser audio frames to Deepgram WebSocket."""
        while not stop_event.is_set():
            try:
                frame = self.session.audio_queue.get(timeout=0.05)
                if frame is None:
                    break
                if muted and muted.is_set():
                  
                    continue
                streaming_stt.send_audio(frame)
            except queue.Empty:
                continue

    def play_tts_stream(self, stream_iter, sample_rate: int,
                        external_stop_event=None):
        """Send TTS audio to browser in chunks."""
        with self._play_lock:
            _using_external = external_stop_event is not None
            stop_event      = external_stop_event or threading.Event()
            monitor_thread  = None

            # Watchdog for instant barge-in stop
            def _watchdog():
                stop_event.wait()
                # No hardware stream to abort, just return

            if not _using_external:
                _wd = threading.Thread(target=_watchdog, daemon=True)
                _wd.start()

            leftover = b""
            for chunk in stream_iter:
                if stop_event.is_set():
                    break
                if not chunk:
                    continue
                chunk = leftover + chunk
                n = (len(chunk) // 2) * 2
                if n:
                    self.session.send_audio_sync(chunk[:n])
                leftover = chunk[n:]

            if not _using_external:
                stop_event.set()

    def get_stats(self):   return self._stats.copy()
    def reset_stats(self): self._stats = {"recordings": 0, "barge_ins": 0,
                                          "denoised": 0, "total_audio_sec": 0.0}
    def get_config(self):  return {"sample_rate": self.sample_rate}


class BrowserTTS:
    """
    Wraps the real TTS to also forward audio to browser.
    Proxies all method calls to the underlying TTS.
    """

    def __init__(self, tts, session: BotSession):
        self._tts     = tts
        self._session = session

    def stream(self, text: str):
        return self._tts.stream(text)

    def stream_synthesize(self, token_iter, audio_io, barge_in_event=None,
                          mic_muted=None):
        return self._tts.stream_synthesize(
            token_iter, audio_io, barge_in_event, mic_muted
        )

    def set_language(self, language_code: str):
        if hasattr(self._tts, "set_language"):
            self._tts.set_language(language_code)

    def get_stats(self):   return self._tts.get_stats()
    def reset_stats(self): self._tts.reset_stats()
    def get_config(self):  return self._tts.get_config()


# ── WebSocket endpoint ────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    session = BotSession(websocket)

    # Start bot in background thread
    bot_thread = threading.Thread(target=session.run_bot, daemon=True)
    bot_thread.start()

    await session.send_event("status", {"msg": "Connected"})

    try:
        while not session.stopped.is_set():
            try:
                msg = await asyncio.wait_for(websocket.receive(), timeout=0.1)
                if msg["type"] == "websocket.receive":
                    if "bytes" in msg and msg["bytes"]:
                        # PCM16 audio frame from browser mic
                        session.audio_queue.put(msg["bytes"])
                    elif "text" in msg and msg["text"]:
                        data = json.loads(msg["text"])
                        if data.get("type") == "stop":
                            session.audio_queue.put(None)
                            break
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    except WebSocketDisconnect:
        pass
    finally:
        session.stopped.set()
        session.audio_queue.put(None)