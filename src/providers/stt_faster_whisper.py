"""
Enhanced STT Provider with Async Support
All features configurable via .env file.
"""
import asyncio
import numpy as np
from typing import Optional
from faster_whisper import WhisperModel


class FasterWhisperSTT:
    """
    Enhanced Faster Whisper STT with async support and full configurability.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        model_name: str = 'small',
        device: str = 'cpu',
        compute_type: str = 'int8',
        language: Optional[str] = None,
        vad_filter: bool = False,
        beam_size: int = 5,
        enable_async: bool = True,
        timeout: float = 30.0,
    ):
        self.enabled = enabled
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.language = language
        self.vad_filter = vad_filter
        self.beam_size = beam_size
        self.enable_async = enable_async
        self.timeout = timeout
        
        # Initialize model
        if self.enabled:
            self.model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type
            )
        else:
            self.model = None
        
        # Stats
        self._stats = {
            "transcriptions": 0,
            "total_duration_sec": 0.0,
            "total_processing_sec": 0.0,
            "errors": 0,
        }
    
    def transcribe_pcm16(self, pcm16: bytes, sample_rate: int) -> str:
        """
        Transcribe PCM16 audio to text.
        
        Args:
            pcm16: PCM16 audio bytes
            sample_rate: Sample rate of the audio
        
        Returns:
            Transcribed text
        """
        if not self.enabled or not self.model:
            return ""
        
        if self.enable_async:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Already in async context
                    return self._transcribe_sync(pcm16, sample_rate)
                else:
                    return asyncio.run(self._transcribe_async(pcm16, sample_rate))
            except RuntimeError:
                # No event loop
                return self._transcribe_sync(pcm16, sample_rate)
        else:
            return self._transcribe_sync(pcm16, sample_rate)
    
    def _transcribe_sync(self, pcm16: bytes, sample_rate: int) -> str:
        """Synchronous transcription."""
        import time
        start_time = time.time()
        
        try:
            # Convert to float32
            audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
            
            # Transcribe
            segments, info = self.model.transcribe(
                audio,
                language=self.language,
                vad_filter=self.vad_filter,
                beam_size=self.beam_size,
            )
            
            # Concatenate segments
            text = ' '.join([s.text.strip() for s in segments if s.text]).strip()
            
            # Update stats
            audio_duration = len(pcm16) / (sample_rate * 2)
            processing_time = time.time() - start_time
            
            self._stats["transcriptions"] += 1
            self._stats["total_duration_sec"] += audio_duration
            self._stats["total_processing_sec"] += processing_time
            
            return text
        
        except Exception as e:
            print(f"[STT] Transcription error: {e}")
            self._stats["errors"] += 1
            return ""
    
    async def _transcribe_async(self, pcm16: bytes, sample_rate: int) -> str:
        """Async transcription (runs sync in executor)."""
        loop = asyncio.get_event_loop()
        return await asyncio.wait_for(
            loop.run_in_executor(None, self._transcribe_sync, pcm16, sample_rate),
            timeout=self.timeout
        )
    
    def get_stats(self) -> dict:
        """Return transcription statistics."""
        stats = self._stats.copy()
        if stats["transcriptions"] > 0:
            stats["avg_processing_sec"] = stats["total_processing_sec"] / stats["transcriptions"]
            stats["real_time_factor"] = stats["total_processing_sec"] / stats["total_duration_sec"] if stats["total_duration_sec"] > 0 else 0
        return stats
    
    def reset_stats(self):
        """Reset statistics."""
        self._stats = {
            "transcriptions": 0,
            "total_duration_sec": 0.0,
            "total_processing_sec": 0.0,
            "errors": 0,
        }
    
    def get_config(self) -> dict:
        """Return current configuration."""
        return {
            "enabled": self.enabled,
            "model_name": self.model_name,
            "device": self.device,
            "compute_type": self.compute_type,
            "language": self.language,
            "vad_filter": self.vad_filter,
            "beam_size": self.beam_size,
            "enable_async": self.enable_async,
            "timeout": self.timeout,
        }
