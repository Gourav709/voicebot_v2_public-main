"""
Filler Audio Manager

Key design:
  - stop() always waits at least MIN_PLAY_MS from thread START (not stream start)
    so even if stream init is slow, the filler gets time to be heard.
  - Uses a threading.Event (_playing_event) that gets set the moment the first
    chunk is written — stop() can wait on this to know audio is actually playing.
  - Dedicated RawOutputStream, no lock contention with TTS stream.
"""
import random
import threading
import time
import numpy as np
import sounddevice as sd
from typing import List, Optional, Dict

MIN_PLAY_MS = 650  # guaranteed minimum audible time before stop() cuts filler


class FillerManager:

    DEFAULT_FILLERS = ["Mm.", "Hmm.", "Ah.", "Um.", "Okay."]

    def __init__(
        self,
        tts,
        audio,
        enabled: bool = True,
        probability: float = 0.4,
        filler_texts: Optional[List[str]] = None,
    ):
        self.tts = tts
        self.audio = audio
        self.enabled = enabled
        self.probability = max(0.0, min(1.0, probability))
        self.filler_texts = filler_texts or self.DEFAULT_FILLERS

        self._cache: Dict[str, bytes] = {}
        self._playback_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._stream: Optional[sd.RawOutputStream] = None
        self._stream_lock = threading.Lock()

        # Set when first audio chunk is written to the stream
        self._playing_event = threading.Event()
        # Timestamp of thread start (not stream start) for MIN_PLAY_MS enforcement
        self._thread_start_time: float = 0.0

        if self.enabled:
            self._warm_up()

    # ─────────────────────────────────────────────────────────────────────────
    # Warm-up
    # ─────────────────────────────────────────────────────────────────────────

    def _warm_up(self):
        print("[FillerManager] Pre-synthesizing fillers...", end=" ", flush=True)
        success = 0
        for text in self.filler_texts:
            try:
                chunks = list(self.tts.stream(text))
                if not chunks:
                    print(f"\n  ✗ '{text}' — no audio returned", end="")
                    continue
                pcm = b"".join(chunks)
                if len(pcm) % 2 != 0:
                    pcm = pcm[:-1]
                pcm = self._trim_silence(pcm)
                duration = len(pcm) / (self.audio.sample_rate * 2)
                if len(pcm) < 800:
                    print(f"\n  ✗ '{text}' — too short after trim ({len(pcm)} bytes)", end="")
                    continue
                self._cache[text] = pcm
                success += 1
                print(f"\n  ✓ '{text}' — {len(pcm)} bytes ({duration:.2f}s after trim)", end="")
            except Exception as e:
                print(f"\n  ✗ '{text}' failed: {e}", end="")
        print(f"\n[FillerManager] Ready — {success}/{len(self.filler_texts)} cached\n")

    def _trim_silence(self, pcm: bytes, threshold: int = 80, frame_ms: int = 20) -> bytes:
        sr = self.audio.sample_rate
        frame_samples = int(sr * frame_ms / 1000)
        samples = np.frombuffer(pcm, dtype=np.int16)
        total_frames = len(samples) // frame_samples
        if total_frames == 0:
            return pcm
        start_frame = 0
        for i in range(total_frames):
            if np.max(np.abs(samples[i * frame_samples:(i + 1) * frame_samples])) > threshold:
                start_frame = max(0, i - 1)
                break
        end_frame = total_frames
        for i in range(total_frames - 1, -1, -1):
            if np.max(np.abs(samples[i * frame_samples:(i + 1) * frame_samples])) > threshold:
                end_frame = min(total_frames, i + 2)
                break
        return samples[start_frame * frame_samples: end_frame * frame_samples].tobytes()

    # ─────────────────────────────────────────────────────────────────────────
    # Public API
    # ─────────────────────────────────────────────────────────────────────────

    def play_filler_async(self) -> bool:
        if not self.enabled or not self._cache:
            return False
        if random.random() > self.probability:
            return False

        text = random.choice(list(self._cache.keys()))
        pcm_bytes = self._cache[text]

        self._stop_event.clear()
        self._playing_event.clear()
        self._thread_start_time = time.time()

        self._playback_thread = threading.Thread(
            target=self._play_direct,
            args=(pcm_bytes,),
            daemon=True,
        )
        self._playback_thread.start()
        return True

    def stop(self):
        """
        Stop filler, but guarantee it has been audible for at least MIN_PLAY_MS.

        Strategy:
          1. Wait up to 300ms for _playing_event — confirms audio actually started.
          2. From thread start time, enforce MIN_PLAY_MS total before cutting.
          3. Then abort the stream and join the thread.
        """
        if not self._playback_thread or not self._playback_thread.is_alive():
            self._playback_thread = None
            return

        # Step 1: wait until we know audio has actually started playing
        # (guards against stop() being called before stream.write() is reached)
        self._playing_event.wait(timeout=0.5)

        # Step 2: enforce minimum audible time from thread start
        if self._thread_start_time > 0:
            elapsed_ms = (time.time() - self._thread_start_time) * 1000
            remaining_ms = MIN_PLAY_MS - elapsed_ms
            if remaining_ms > 0:
                time.sleep(remaining_ms / 1000)

        # Step 3: cut it
        self._stop_event.set()
        with self._stream_lock:
            if self._stream is not None:
                try:
                    # Do NOT abort() — it truncates buffered audio that hasn't
                    # played yet (Windows WASAPI high latency = ~180ms buffer).
                    # Instead wait for the buffer to drain, then stop() cleanly.
                    time.sleep(0.22)  # 180ms high latency + 40ms margin
                    self._stream.stop()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=2.0)
        self._playback_thread = None

    # ─────────────────────────────────────────────────────────────────────────
    # Internal playback
    # ─────────────────────────────────────────────────────────────────────────

    def _play_direct(self, pcm_bytes: bytes):
        chunk_size = 3200  # 100ms @ 16kHz
        try:
            stream = sd.RawOutputStream(
                samplerate=self.audio.sample_rate,
                channels=1,
                dtype="int16",
                blocksize=self.audio.buffer_size,
            )
            stream.start()

            with self._stream_lock:
                self._stream = stream

            offset = 0
            first_chunk = True
            while offset < len(pcm_bytes):
                if self._stop_event.is_set():
                    break
                chunk = pcm_bytes[offset: offset + chunk_size]
                if len(chunk) % 2 != 0:
                    chunk = chunk[:-1]
                if chunk:
                    try:
                        stream.write(chunk)
                        if first_chunk:
                            # Signal that audio is now actually flowing
                            self._playing_event.set()
                            first_chunk = False
                    except sd.PortAudioError:
                        break
                offset += chunk_size

        except Exception as e:
            if not self._stop_event.is_set():
                print(f"[FillerManager] Playback error: {e}")
        finally:
            self._playing_event.set()  # unblock stop() even on error
            with self._stream_lock:
                if self._stream is not None:
                    try:
                        self._stream.stop()
                        self._stream.close()
                    except Exception:
                        pass
                    self._stream = None

    # ─────────────────────────────────────────────────────────────────────────

    def cached_count(self) -> int:
        return len(self._cache)

    def get_config(self) -> dict:
        return {
            "enabled": self.enabled,
            "probability": self.probability,
            "filler_count": len(self.filler_texts),
            "cached_count": self.cached_count(),
        }