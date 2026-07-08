"""
Sarvam AI TTS Provider
Indian-language-first TTS, built for Hinglish and Indian-accented English.
Togglable via TTS_PROVIDER=sarvam in .env

Models:
  bulbul:v3 (recommended) — 30+ voices, temperature control, max 2500 chars
      Speakers (capitalized): Shubh, Priya, Neha, Rahul, Pooja, Rohan, Simran,
      Kavya, Amit, Dev, Ishita, Shreya, Ratan, Varun, Anand, Tanya, Tarun...
      Supports: pace (0.5–2.0), temperature (0.01–2.0)
      Does NOT support: pitch, loudness, enable_preprocessing

  bulbul:v2 (legacy) — fewer voices, pitch/loudness control, max 1500 chars
      Speakers (lowercase): anushka, manisha, vidya, arya (F); abhilash, karun, hitesh (M)
      Supports: pitch (-0.75–0.75), loudness (0.3–3.0), pace (0.3–3.0), enable_preprocessing
      Does NOT support: temperature
"""
import time
import base64
import requests
from typing import Iterator, Optional


class SarvamTTS:
    """
    Sarvam AI TTS client.
    Payload is built dynamically based on the model version to avoid 400 errors.
    """

    def __init__(
        self,
        enabled: bool = True,
        api_key: str = "",
        model: str = "bulbul:v2",
        speaker: str = "anushka",  # v2 is 2.7x faster than v3
        language: str = "en-IN",
        # v2-only params
        pitch: float = 0.0,
        loudness: float = 1.5,
        enable_preprocessing: bool = True,
        # shared param
        pace: float = 1.1,
        # v3-only param
        temperature: float = 0.6,
        timeout: float = 20.0,
        enable_async: bool = True,
    ):
        if enabled and not api_key:
            raise RuntimeError("SARVAM_API_KEY is missing in .env")

        self.enabled = enabled
        self.api_key = api_key
        self.model = model
        self.speaker = speaker
        self.language = language
        self.pitch = pitch
        self.loudness = loudness
        self.enable_preprocessing = enable_preprocessing
        self.pace = pace
        self.temperature = temperature
        self.timeout = timeout
        self.enable_async = enable_async

        self._is_v3 = model == "bulbul:v3"

        # v3 has a 2500 char limit, v2 has 1500
        self._max_chars = 2490 if self._is_v3 else 1490

        self._url = "https://api.sarvam.ai/text-to-speech"

        self._stats = {
            "synthesized": 0,
            "total_chars": 0,
            "total_time_sec": 0.0,
            "errors": 0,
        }

    def _build_payload(self, text: str) -> dict:
        """
        Build request payload based on model version.
        v3 and v2 support different parameters — mixing them causes 400 errors.
        """
        base = {
            "text": text,                        # single string, NOT a list
            "target_language_code": self.language,
            "speaker": self.speaker,
            "speech_sample_rate": 16000,
            "model": self.model,
            "pace": self.pace,
        }

        if self._is_v3:
            # bulbul:v3 — pitch, loudness, enable_preprocessing are NOT supported
            base["temperature"] = self.temperature
        else:
            # bulbul:v2 — temperature is NOT supported
            base["pitch"] = self.pitch
            base["loudness"] = self.loudness
            base["enable_preprocessing"] = self.enable_preprocessing

        return base

    def stream(self, text: str) -> Iterator[bytes]:
        """
        Synthesize text and yield audio as a single PCM chunk.
        Sarvam REST API is non-streaming; we yield one chunk per call,
        which is compatible with AudioIO.play_tts_stream().

        Args:
            text: Text to synthesize (English, Hindi, or Hinglish)

        Yields:
            Raw PCM16 audio bytes at 16000 Hz
        """
        if not self.enabled:
            return

        if not text or not text.strip():
            return

        audio_bytes = self._synthesize(text)
        if audio_bytes:
            yield audio_bytes

    def _synthesize(self, text: str) -> Optional[bytes]:
        """Call Sarvam API and return raw PCM16 bytes."""
        start_time = time.time()

        chunks = self._split_text(text, max_chars=self._max_chars)
        all_audio = b""

        headers = {
            "api-subscription-key": self.api_key,
            "Content-Type": "application/json",
        }

        for chunk in chunks:
            payload = self._build_payload(chunk)

            try:
                response = requests.post(
                    self._url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )
                response.raise_for_status()
                result = response.json()

                audios = result.get("audios", [])
                if not audios:
                    print("[SarvamTTS] No audio in response")
                    continue

                # Response is base64-encoded WAV; strip 44-byte header for raw PCM
                wav_bytes = base64.b64decode(audios[0])
                pcm_bytes = self._strip_wav_header(wav_bytes)
                all_audio += pcm_bytes

            except Exception as e:
                self._stats["errors"] += 1
                print(f"[SarvamTTS] Error: {e}")
                raise

        if all_audio:
            processing_time = time.time() - start_time
            self._stats["synthesized"] += 1
            self._stats["total_chars"] += len(text)
            self._stats["total_time_sec"] += processing_time

        return all_audio if all_audio else None

    def _strip_wav_header(self, wav_bytes: bytes) -> bytes:
        """Strip standard 44-byte WAV header to get raw PCM16 data."""
        if len(wav_bytes) > 44 and wav_bytes[:4] == b"RIFF":
            return wav_bytes[44:]
        return wav_bytes

    def _split_text(self, text: str, max_chars: int):
        """Split long text into chunks at sentence boundaries."""
        if len(text) <= max_chars:
            return [text]

        chunks = []
        sentences = text.replace("। ", "।\n").replace(". ", ".\n").split("\n")
        current = ""

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(current) + len(sentence) + 1 <= max_chars:
                current = (current + " " + sentence).strip()
            else:
                if current:
                    chunks.append(current)
                current = sentence

        if current:
            chunks.append(current)

        return chunks if chunks else [text[:max_chars]]

    def set_language(self, language_code: str):
        """
        Dynamically switch TTS language per turn.
        Called by the orchestrator when STT detects a language change.
        language_code: BCP-47 code e.g. 'hi-IN', 'en-IN'
        """
        supported = [
            "hi-IN", "en-IN", "ta-IN", "te-IN", "kn-IN",
            "ml-IN", "mr-IN", "bn-IN", "gu-IN", "or-IN", "pa-IN",
        ]
        if language_code in supported:
            self.language = language_code
        else:
            # Fallback: try prefix match (e.g. 'en' -> 'en-IN')
            prefix = language_code.split("-")[0]
            matched = next((s for s in supported if s.startswith(prefix)), None)
            self.language = matched if matched else "en-IN"

    def get_stats(self) -> dict:
        stats = self._stats.copy()
        if stats["synthesized"] > 0:
            stats["avg_time_sec"] = stats["total_time_sec"] / stats["synthesized"]
            stats["avg_chars"] = stats["total_chars"] / stats["synthesized"]
        return stats

    def reset_stats(self):
        self._stats = {
            "synthesized": 0,
            "total_chars": 0,
            "total_time_sec": 0.0,
            "errors": 0,
        }

    def get_config(self) -> dict:
        return {
            "enabled": self.enabled,
            "model": self.model,
            "speaker": self.speaker,
            "language": self.language,
            "pace": self.pace,
            "timeout": self.timeout,
        }
    def stream_synthesize(
        self,
        token_iter,
        audio_io,
        barge_in_event=None,
        mic_muted=None,
    ):
        """
        Streaming LLM→TTS pipeline.

        Consumes tokens from token_iter, detects sentence boundaries,
        fires a Sarvam TTS call per sentence, and plays audio in real time.
        Sentence 2 TTS call starts while sentence 1 is still playing.

        Args:
            token_iter:      Iterator yielding text tokens (from llm.stream_complete)
            audio_io:        AudioIO instance for playback
            barge_in_event:  threading.Event — if set, stop playback immediately
        """
        import re
        import queue
        import threading

        SPLIT_RE  = re.compile(r'(?<=[.!?।])\s+')
        MIN_CHARS = 12   # don't fire TTS on very short fragments

        # Two-stage pipeline:
        #   sentence_queue → [synth worker] → pcm_queue → [play worker]
        # Sentence 2 synthesis starts while sentence 1 is still playing.
        sentence_queue = queue.Queue(maxsize=8)
        pcm_queue      = queue.Queue(maxsize=4)
        stopped        = threading.Event()
        full_text      = []

        def synth_worker():
            """Converts sentence text → PCM bytes."""
            while True:
                item = sentence_queue.get()
                if item is None:
                    pcm_queue.put(None)   # propagate stop signal
                    sentence_queue.task_done()
                    break
                if stopped.is_set():
                    sentence_queue.task_done()
                    continue
                try:
                    pcm = self._synthesize(item)
                    if pcm and not stopped.is_set():
                        pcm_queue.put(pcm)
                except Exception as e:
                    print(f"[TTS stream] Synth error: {e}")
                finally:
                    sentence_queue.task_done()

        def play_worker():
            """Plays PCM bytes in order."""
            while True:
                item = pcm_queue.get()
                if item is None:
                    pcm_queue.task_done()
                    break
                if stopped.is_set():
                    pcm_queue.task_done()
                    continue
                try:
                    # Unmute mic during playback — barge-in is live
                    if mic_muted:
                        mic_muted.clear()
                    # Clear any stale barge-in from synthesis phase
                    if barge_in_event:
                        barge_in_event.clear()
                    audio_io.play_tts_stream(
                        stream_iter=iter([item]),
                        sample_rate=audio_io.sample_rate,
                        external_stop_event=barge_in_event,
                    )
                    # Remute after playback before next synthesis
                    if mic_muted:
                        mic_muted.set()
                    if barge_in_event and barge_in_event.is_set():
                        stopped.set()
                except Exception as e:
                    print(f"[TTS stream] Play error: {e}")
                finally:
                    pcm_queue.task_done()

        synth_t = threading.Thread(target=synth_worker, daemon=True)
        play_t  = threading.Thread(target=play_worker,  daemon=True)
        synth_t.start()
        play_t.start()

        # ── Token consumer + sentence splitter ───────────────────────────────
        buffer = ''
        try:
            for token in token_iter:
                if stopped.is_set():
                    break
                buffer     += token
                full_text.append(token)

                # Check for sentence boundary
                parts = SPLIT_RE.split(buffer)
                if len(parts) > 1:
                    for sentence in parts[:-1]:
                        sentence = sentence.strip()
                        if sentence and len(sentence) >= MIN_CHARS:
                            sentence_queue.put(sentence)
                    buffer = parts[-1]  # remainder

            # Fire any remaining text
            if buffer.strip() and len(buffer.strip()) >= MIN_CHARS and not stopped.is_set():
                sentence_queue.put(buffer.strip())
            elif buffer.strip() and not stopped.is_set():
                # Too short on its own — append to last sentence if possible
                # or fire anyway
                sentence_queue.put(buffer.strip())

        finally:
            sentence_queue.put(None)   # stop signal
            synth_t.join()
            play_t.join()

        return ''.join(full_text).strip()