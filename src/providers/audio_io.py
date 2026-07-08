"""
Enhanced Audio I/O Module with Async Support and Denoising
All features are configurable via .env file.
"""
import threading
import time
import asyncio
import numpy as np
import sounddevice as sd
import webrtcvad
from typing import Optional, Tuple, Iterator
from src.providers.denoiser import AudioDenoiser


class AudioIO:
    """
    Enhanced audio input/output handler.
    
    Features:
    - Configurable VAD-based recording
    - Optional barge-in detection during playback
    - Optional audio denoising
    - Async support for non-blocking operations
    - All parameters controlled via .env
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        vad_aggressiveness: int = 2,
        end_silence_ms: int = 800,
        max_utterance_sec: int = 20,
        # Barge-in settings
        enable_barge_in: bool = True,
        barge_in_trigger_ms: int = 120,
        barge_in_sensitivity: int = 2,
        # Denoiser
        denoiser: Optional[AudioDenoiser] = None,
        # Performance
        enable_async: bool = True,
        buffer_size: int = 4096,
        # Logging
        log_audio_stats: bool = False,
    ):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.vad = webrtcvad.Vad(vad_aggressiveness)
        self.end_silence_ms = end_silence_ms
        self.max_utt_sec = max_utterance_sec
        
        # Barge-in
        self.enable_barge_in = enable_barge_in
        self.barge_in_trigger_ms = barge_in_trigger_ms
        self.barge_in_vad = webrtcvad.Vad(barge_in_sensitivity) if enable_barge_in else None
        
        # Denoiser
        self.denoiser = denoiser
        
        # Performance
        self.enable_async = enable_async
        self.buffer_size = buffer_size
        
        # Logging
        self.log_audio_stats = log_audio_stats
        
        # Internal state
        self.frame_len = int(sample_rate * frame_ms / 1000)
        self.frame_bytes = self.frame_len * 2  # int16 mono
        self._play_lock = threading.Lock()
        
        # Stats
        self._stats = {
            "recordings": 0,
            "barge_ins": 0,
            "denoised": 0,
            "total_audio_sec": 0.0,
        }
    
    def record_utterance(self) -> Tuple[bytes, int]:
        """
        Record user utterance using VAD.
        
        Returns:
            (pcm16_bytes, sample_rate)
        """
        if self.enable_async:
            # Run in asyncio if available
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in async context, can't use asyncio.run
                    return self._record_sync()
                else:
                    return asyncio.run(self._record_async())
            except RuntimeError:
                # No event loop, use sync
                return self._record_sync()
        else:
            return self._record_sync()
    
    def stream_to_stt(self, streaming_stt, stop_event: threading.Event,
                      muted: threading.Event = None) -> None:
        """
        Streaming mode recording — forwards mic frames directly to
        DeepgramStreamingSTT instead of buffering locally.
        Runs until stop_event is set. Replaces record_utterance() in streaming mode.
        VAD, endpointing and denoising are handled by Deepgram server-side.
        """
        def callback(indata, frames, time_info, status):
            if stop_event.is_set():
                return
            if muted and muted.is_set():
                return   # bot is speaking — discard mic input
            pcm16 = (np.clip(indata[:, 0], -1, 1) * 32767).astype(np.int16).tobytes()
            streaming_stt.send_audio(pcm16)

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.frame_len,
            callback=callback,
        ):
            while not stop_event.is_set():
                time.sleep(0.05)

    def _record_sync(self) -> Tuple[bytes, int]:
        """Synchronous recording implementation."""
        max_frames = int((self.max_utt_sec * 1000) / self.frame_ms)
        end_silence_frames = int(self.end_silence_ms / self.frame_ms)
        
        collected = bytearray()
        speech_started = False
        silence_run = 0
        
        def callback(indata, frames, time_info, status):
            nonlocal collected, speech_started, silence_run
            mono = indata[:, 0]
            pcm16 = (np.clip(mono, -1, 1) * 32767).astype(np.int16).tobytes()
            is_speech = self.vad.is_speech(pcm16, self.sample_rate)
            
            if is_speech:
                speech_started = True
                silence_run = 0
                collected.extend(pcm16)
            else:
                if speech_started:
                    silence_run += 1
                    collected.extend(pcm16)
        
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.frame_len,
            callback=callback,
        ):
            frames = 0
            while frames < max_frames:
                time.sleep(self.frame_ms / 1000)
                frames += 1
                if speech_started and silence_run >= end_silence_frames:
                    break
        
        if not collected or not speech_started:
            return b"", self.sample_rate
        
        # Trim trailing silence
        keep_tail_ms = 200
        trim_ms = max(self.end_silence_ms - keep_tail_ms, 0)
        trim_frames = int(trim_ms / self.frame_ms)
        trim_bytes = trim_frames * self.frame_bytes
        if trim_bytes > 0 and len(collected) > trim_bytes:
            collected = collected[:-trim_bytes]
        
        pcm16 = bytes(collected)
        
        # Denoise if enabled
        if self.denoiser and self.denoiser.enabled:
            pcm16 = self.denoiser.denoise_pcm16(pcm16)
            self._stats["denoised"] += 1
        
        # Update stats
        self._stats["recordings"] += 1
        self._stats["total_audio_sec"] += len(pcm16) / (self.sample_rate * 2)
        
        if self.log_audio_stats:
            print(f"[AudioIO] Recorded {len(pcm16)} bytes, {len(pcm16)/(self.sample_rate*2):.2f}s")
        
        return pcm16, self.sample_rate
    
    async def _record_async(self) -> Tuple[bytes, int]:
        """Async recording implementation (runs sync recording in executor)."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._record_sync)
    
    def _barge_in_monitor(self, stop_event: threading.Event):
        """
        Monitor microphone during playback for barge-in detection.
        
        Args:
            stop_event: Event to set when barge-in detected
        """
        if not self.enable_barge_in or not self.barge_in_vad:
            return
        
        trigger_frames = max(1, int(self.barge_in_trigger_ms / self.frame_ms))
        speech_run = 0
        
        def cb(indata, frames, time_info, status):
            nonlocal speech_run
            mono = indata[:, 0]
            pcm16 = (np.clip(mono, -1, 1) * 32767).astype(np.int16).tobytes()
            is_speech = self.barge_in_vad.is_speech(pcm16, self.sample_rate)
            
            if is_speech:
                speech_run += 1
                if speech_run >= trigger_frames:
                    self._stats["barge_ins"] += 1
                    if self.log_audio_stats:
                        print(f"[AudioIO] Barge-in detected after {speech_run} frames")
                    stop_event.set()  # playback loop checks this and breaks cleanly
                    return            # exit monitor thread — job done
            else:
                speech_run = 0
        
        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.frame_len,
            callback=cb,
        ):
            while not stop_event.is_set():
                time.sleep(self.frame_ms / 1000)
    
    def play_tts_stream(self, stream_iter: Iterator[bytes], sample_rate: int,
                        external_stop_event: threading.Event = None):
        """
        Play streaming TTS audio with optional barge-in.
        
        Args:
            stream_iter: Iterator yielding PCM16 chunks
            sample_rate: Sample rate of the audio
        """


        with self._play_lock:
            # Use external stop event if provided (streaming mode barge-in)
            # otherwise create internal one for batch mode VAD monitor
            # Use external stop event if provided — but track whether it's external
            # so we don't accidentally set it in the finally block
            _using_external = external_stop_event is not None
            stop_event      = external_stop_event or threading.Event()
            monitor_thread  = None

            if self.enable_barge_in and not _using_external:
                monitor_thread = threading.Thread(
                    target=self._barge_in_monitor,
                    args=(stop_event,),
                    daemon=True
                )
                monitor_thread.start()
            
            # Callback-based playback — stops instantly on barge-in
            # The callback runs on the audio thread; when stop_event is set
            # it outputs silence immediately, no buffer-drain delay.
            try:
                # Buffer all audio into a bytearray for callback consumption
                audio_buf  = bytearray()
                for chunk in stream_iter:
                    if not chunk:
                        continue
                    chunk = bytes(chunk)
                    n = (len(chunk) // 2) * 2
                    audio_buf.extend(chunk[:n])

                buf_pos  = [0]   # mutable pointer for callback
                finished = threading.Event()

                def _callback(outdata, frames, time_info, status):
                    if stop_event.is_set():
                        outdata[:] = b"\x00" * len(outdata)
                        finished.set()
                        raise sd.CallbackStop()
                    needed = frames * 2   # int16 = 2 bytes/sample
                    pos    = buf_pos[0]
                    chunk  = bytes(audio_buf[pos:pos + needed])
                    if len(chunk) < needed:
                        chunk = chunk + b"\x00" * (needed - len(chunk))
                        outdata[:] = chunk
                        finished.set()
                        raise sd.CallbackStop()
                    outdata[:] = chunk
                    buf_pos[0] += needed

                with sd.RawOutputStream(
                    samplerate=sample_rate,
                    channels=1,
                    dtype="int16",
                    blocksize=self.buffer_size,
                    callback=_callback,
                    finished_callback=finished.set,
                ):
                    finished.wait()



            
            finally:
                # Only set stop_event if it's our internal one
                if not _using_external:
                    stop_event.set()
                if monitor_thread:
                    monitor_thread.join(timeout=0.5)
    
    async def play_tts_stream_async(self, stream_iter: Iterator[bytes], sample_rate: int):
        """
        Async wrapper for play_tts_stream.
        
        Args:
            stream_iter: Iterator yielding PCM16 chunks
            sample_rate: Sample rate of the audio
        """
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.play_tts_stream, stream_iter, sample_rate)
    
    def get_stats(self) -> dict:
        """Return audio statistics."""
        return self._stats.copy()
    
    def reset_stats(self):
        """Reset statistics counters."""
        self._stats = {
            "recordings": 0,
            "barge_ins": 0,
            "denoised": 0,
            "total_audio_sec": 0.0,
        }
    
    def get_config(self) -> dict:
        """Return current configuration."""
        config = {
            "sample_rate": self.sample_rate,
            "frame_ms": self.frame_ms,
            "vad_aggressiveness": self.vad._aggressiveness,
            "end_silence_ms": self.end_silence_ms,
            "max_utterance_sec": self.max_utt_sec,
            "enable_barge_in": self.enable_barge_in,
            "barge_in_trigger_ms": self.barge_in_trigger_ms,
            "enable_async": self.enable_async,
            "buffer_size": self.buffer_size,
        }
        
        if self.denoiser:
            config["denoiser"] = self.denoiser.get_config()
        
        return config