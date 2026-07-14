"""
Deepgram STT Provider — batch and streaming modes.

DEEPGRAM_STT_MODE=batch     → original HTTP POST (default, safe fallback)
DEEPGRAM_STT_MODE=streaming → WebSocket streaming (lower latency, ~300ms vs ~1500ms)

Batch mode:   language=en + detect_language=true  (confirmed working for Hindi+English)
Streaming mode: language=hi  (detect_language not supported in streaming API)
"""
import asyncio
import json
import threading
import time
import requests
from typing import Callable, Optional, Tuple
from src.providers.language_detector import LanguageDetector

# ─────────────────────────────────────────────────────────────────────────────
# Batch STT (original — unchanged)
# ─────────────────────────────────────────────────────────────────────────────

class DeepgramSTT:
    """
    Batch HTTP STT. Records full utterance then sends to Deepgram.
    Uses language=en + detect_language=true for Hindi+English support.
    """

    def __init__(
        self,
        enabled: bool = True,
        api_key: str = "",
        model: str = "nova-2-general",
        language: str = "en",
        multilingual: bool = True,
        punctuate: bool = True,
        smart_format: bool = True,
        timeout: float = 15.0,
        enable_async: bool = True,
    ):
        if enabled and not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is missing in .env")

        self.enabled      = enabled
        self.api_key      = api_key
        self.model        = model
        self.multilingual = multilingual
        self.punctuate    = punctuate
        self.smart_format = smart_format
        self.timeout      = timeout
        self.enable_async = enable_async
        self.language     = language   # en + detect_language=true — confirmed working

        self._url = "https://api.deepgram.com/v1/listen"
        self._stats = {
            "transcriptions": 0,
            "total_duration_sec": 0.0,
            "total_processing_sec": 0.0,
            "errors": 0,
        }

    def transcribe_pcm16(self, pcm16: bytes, sample_rate: int) -> str:
        transcript, _ = self.transcribe_with_language(pcm16, sample_rate)
        return transcript

    def transcribe_with_language(self, pcm16: bytes, sample_rate: int) -> Tuple[str, str]:
        """Returns (transcript, detected_language) where language is 'en-IN' or 'hi-IN'."""
        if not self.enabled or not pcm16:
            return "", "en-IN"

        if self.enable_async:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return self._transcribe_sync(pcm16, sample_rate)
                return asyncio.run(self._transcribe_async(pcm16, sample_rate))
            except RuntimeError:
                return self._transcribe_sync(pcm16, sample_rate)
        return self._transcribe_sync(pcm16, sample_rate)

    def _transcribe_sync(self, pcm16: bytes, sample_rate: int) -> Tuple[str, str]:
        start = time.time()
        params = {
            "model":           self.model,
            "detect_language": "true",
            "punctuate":       "true" if self.punctuate    else "false",
            "smart_format":    "true" if self.smart_format else "false",
            "encoding":        "linear16",
            "sample_rate":     sample_rate,
            "channels":        1,
        }
        if not self.multilingual and self.language:
           params["language"] = self.language
        headers = {
            "Authorization": f"Token {self.api_key}",
            "Content-Type":  "audio/raw",
        }
        try:
            r = requests.post(self._url, params=params, headers=headers,
                              data=pcm16, timeout=self.timeout)
            r.raise_for_status()
            result   = r.json()
            channel  = result.get("results", {}).get("channels", [{}])[0]
            alt      = channel.get("alternatives", [{}])[0]
            transcript = alt.get("transcript", "").strip()
            
            raw_lang = channel.get("detected_language", "en")

            LANGUAGE_MAP = {
    "en": "en-IN",
    "hi": "hi-IN",
    "te": "te-IN",
    "ta": "ta-IN",
    "or": "or-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "bn": "bn-IN",
    "mr": "mr-IN",
    "gu": "gu-IN",
}

            detected = LANGUAGE_MAP.get(raw_lang, "en-IN")
            print(f"Detected language: {raw_lang} -> {detected}")

            duration = len(pcm16) / (sample_rate * 2)
            self._stats["transcriptions"]       += 1
            self._stats["total_duration_sec"]   += duration
            self._stats["total_processing_sec"] += time.time() - start
            return transcript, detected

        except Exception as e:
            self._stats["errors"] += 1
            print(f"[DeepgramSTT] Error: {e}")
            raise

    async def _transcribe_async(self, pcm16: bytes, sample_rate: int) -> Tuple[str, str]:
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._transcribe_sync, pcm16, sample_rate),
            timeout=self.timeout,
        )

    def get_stats(self) -> dict:
        stats = self._stats.copy()
        if stats["transcriptions"] > 0:
            stats["avg_processing_sec"] = (stats["total_processing_sec"]
                                           / stats["transcriptions"])
            stats["real_time_factor"]   = (stats["total_processing_sec"]
                                           / stats["total_duration_sec"]
                                           if stats["total_duration_sec"] > 0 else 0)
        return stats

    def reset_stats(self):
        self._stats = {"transcriptions": 0, "total_duration_sec": 0.0,
                       "total_processing_sec": 0.0, "errors": 0}

    def get_config(self) -> dict:
        return {"enabled": self.enabled, "model": self.model,
                "language": self.language, "punctuate": self.punctuate,
                "smart_format": self.smart_format, "timeout": self.timeout}


# ─────────────────────────────────────────────────────────────────────────────
# Streaming STT
# ─────────────────────────────────────────────────────────────────────────────

class DeepgramStreamingSTT:
    """
    WebSocket streaming STT. Audio frames are sent live as you speak.
    Deepgram handles VAD, endpointing, and denoising server-side.

    Usage:
        stt = DeepgramStreamingSTT(api_key=..., on_utterance=my_callback)
        stt.start()                          # open WebSocket
        stt.send_audio(pcm16_frame)          # call from audio callback
        stt.stop()                           # close WebSocket

    on_utterance(transcript: str, language: str) is called when
    speech_final fires — equivalent to record_utterance() returning.
    """

    WS_URL_TEMPLATE = (
    "wss://api.deepgram.com/v1/listen"
    "?model={model}"
    "&language=en"
    "&punctuate=true"
    "&smart_format=true"
    "&encoding=linear16"
    "&sample_rate={sample_rate}"
    "&channels=1"
    "&interim_results=true"
    "&endpointing={endpointing}"
    "&utterance_end_ms={utterance_end_ms}"
    "&vad_events=true"
)
    def __init__(
        self,
        enabled: bool = True,
        api_key: str = "",
        model: str = "nova-2-general",
        sample_rate: int = 16000,
        endpointing_ms: int = 300,
        utterance_end_ms: int = 1000,
        on_utterance: Optional[Callable[[str, str], None]] = None,
        on_partial: Optional[Callable[[str], None]] = None,
    ):
        if enabled and not api_key:
            raise RuntimeError("DEEPGRAM_API_KEY is missing in .env")

        self.enabled          = enabled
        self.api_key          = api_key
        self.model            = model
        self.sample_rate      = sample_rate
        self.endpointing_ms   = endpointing_ms
        self.utterance_end_ms = utterance_end_ms
        self.on_utterance     = on_utterance   # callback: (transcript, language) → None
        self.on_partial       = on_partial     # optional callback for partials

        self._ws              = None
        self._ws_thread       = None
        self._connected       = threading.Event()
        self._accumulated     = []   # Final transcripts within current utterance
        self._speech_start    = None

        self._stats = {
            "transcriptions": 0,
            "total_duration_sec": 0.0,
            "total_processing_sec": 0.0,
            "errors": 0,
        }
        self.language_detector = LanguageDetector()
    # ── Public API ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open WebSocket connection. Returns True when connected."""
        if not self.enabled:
            return False
        try:
            import websocket
        except ImportError:
            raise RuntimeError("websocket-client not installed. Run: pip install websocket-client")

        url = self.WS_URL_TEMPLATE.format(
            model=self.model,
            sample_rate=self.sample_rate,
            endpointing=self.endpointing_ms,
            utterance_end_ms=self.utterance_end_ms,
        )
        self._ws = websocket.WebSocketApp(
            url,
            header={"Authorization": f"Token {self.api_key}"},
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws_thread = threading.Thread(
            target=self._ws.run_forever,
            kwargs={"ping_interval": 10},
            daemon=True,
        )
        self._ws_thread.start()
        connected = self._connected.wait(timeout=5.0)
        if not connected:
            raise RuntimeError("[DeepgramStreamingSTT] Connection timed out")
        return True

    def send_audio(self, pcm16_frame: bytes) -> None:
        """Send a raw PCM16 audio frame to Deepgram. Call from sounddevice callback."""
        if self._ws and self._connected.is_set():
            try:
                import websocket as ws_lib
                self._ws.send(pcm16_frame, ws_lib.ABNF.OPCODE_BINARY)
            except Exception:
                pass

    def stop(self) -> None:
        """Close WebSocket connection cleanly."""
        if self._ws:
            try:
                self._ws.send(json.dumps({"type": "CloseStream"}))
                time.sleep(0.3)
            except Exception:
                pass
            self._ws.close()
        self._connected.clear()

    # ── WebSocket handlers ────────────────────────────────────────────────────

    def _on_open(self, ws):
        self._connected.set()

    def _on_message(self, ws, message):
        try:
            data     = json.loads(message)
            msg_type = data.get("type", "")

            if msg_type == "SpeechStarted":
                if not self._speech_start:
                    self._speech_start = time.time()

            elif msg_type == "Results":
                ch           = data.get("channel", {})
                alt          = ch.get("alternatives", [{}])[0]
                transcript   = alt.get("transcript", "").strip()
                is_final     = data.get("is_final", False)
                speech_final = data.get("speech_final", False)

                if not transcript:
                    return

                if speech_final:
                    self._fire_utterance(transcript)

                elif is_final:
                    # Accumulate — more speech may follow in same utterance
                    self._accumulated.append(transcript)

                else:
                    # Partial — notify UI only, don't act on it
                    if self.on_partial:
                        self.on_partial(transcript)

            elif msg_type == "UtteranceEnd":
                # Fallback trigger when speech_final didn't fire
                if self._accumulated:
                    self._fire_utterance("")   # fire with accumulated text

        except Exception as e:
            print(f"[DeepgramStreamingSTT] Message error: {e}")

    def _fire_utterance(self, last_fragment: str) -> None:
        """Build full transcript and call on_utterance callback."""
        parts = self._accumulated[:]

        if last_fragment and last_fragment not in parts:
         parts.append(last_fragment)

        full_transcript = " ".join(parts).strip()

        print("\n========== RAW STT ==========")
        print(full_transcript)
        print("=============================\n")

        if not full_transcript:
         return

    # Ignore single-character noise
        if len(full_transcript.strip()) <= 1:
          return

        self._accumulated = []
        self._speech_start = None

    # ----------------------------------------------------
    # Language Detection (Hindi + Hinglish + English)
    # ----------------------------------------------------

        text = full_transcript.lower()

    # Detect Devanagari characters
        hindi_chars = sum(
          1 for c in full_transcript
          if '\u0900' <= c <= '\u097F'
    )

    # Common Hinglish words
        hindi_keywords = [
        "kya",
        "hai",
        "haan",
        "han",
        "nahi",
        "nahin",
        "kaise",
        "kyu",
        "kyon",
        "kitna",
        "kitne",
        "mera",
        "meri",
        "mere",
        "mujhe",
        "tum",
        "aap",
        "karna",
        "karni",
        "karo",
        
        
        
    ]

        hinglish_score = 0

        for word in hindi_keywords:
          if word in text:
            hinglish_score += 1

        if hindi_chars > 2:
          detected = "hi-IN"

        elif hinglish_score >= 2 and "what" not in text and "how" not in text:
           detected = "hi-IN"

        else:
           detected = "en-IN"

        print(f"[Language Detection] {detected}")
        print(f"[Transcript] {full_transcript}")

    # ----------------------------------------------------

        duration = len(full_transcript) / 10

        self._stats["transcriptions"] += 1
        self._stats["total_duration_sec"] += duration

        if self.on_utterance:
          self.on_utterance(full_transcript, detected)

    def _on_error(self, ws, error):
        err = str(error)
        if "opcode=8" in err or "fin=1" in err:
            return   # normal close — not an error
        print(f"[DeepgramStreamingSTT] Error: {error}")
        self._stats["errors"] += 1

    def _on_close(self, ws, code, msg):
        self._connected.clear()

    # ── Stats (same interface as batch STT) ───────────────────────────────────

    def get_stats(self) -> dict:
        return self._stats.copy()

    def reset_stats(self):
        self._stats = {"transcriptions": 0, "total_duration_sec": 0.0,
                       "total_processing_sec": 0.0, "errors": 0}

    def get_config(self) -> dict:
        return {
            "enabled":         self.enabled,
            "model":           self.model,
            "language":        "hi (streaming)",
            "endpointing_ms":  self.endpointing_ms,
            "utterance_end_ms": self.utterance_end_ms,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Factory — used by main.py
# ─────────────────────────────────────────────────────────────────────────────

def create_stt(mode: str, **kwargs):
    """
    Factory function. mode = 'batch' or 'streaming'.
    kwargs passed to the appropriate class.
    """
    if mode == "streaming":
        streaming_keys = {"enabled", "api_key", "model", "sample_rate",
                          "endpointing_ms", "utterance_end_ms"}
        return DeepgramStreamingSTT(**{k: v for k, v in kwargs.items()
                                       if k in streaming_keys})
    else:
        batch_keys = {"enabled", "api_key", "model", "language", "multilingual",
                      "punctuate", "smart_format", "timeout", "enable_async"}
        return DeepgramSTT(**{k: v for k, v in kwargs.items()
                               if k in batch_keys})