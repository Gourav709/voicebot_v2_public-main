"""
Enhanced TTS Provider with Async Support
All features configurable via .env file.
"""
import asyncio
import aiohttp
import requests
from typing import Iterator, Optional, AsyncIterator
import time


class ElevenLabsTTS:
    """
    Enhanced ElevenLabs TTS client with async support and configurability.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        api_key: str = "",
        voice_id: str = "",
        model_id: str = "eleven_turbo_v2_5",
        output_format: str = "pcm_16000",
        stability: float = 0.35,
        similarity_boost: float = 0.8,
        style: float = 0.0,
        speaker_boost: bool = True,
        timeout: float = 60.0,
        enable_streaming: bool = True,
        enable_async: bool = True,
    ):
        if enabled:
            if not api_key:
                raise RuntimeError("ELEVENLABS_API_KEY is missing in .env")
            if not voice_id:
                raise RuntimeError("ELEVENLABS_VOICE_ID is missing in .env")
        
        self.enabled = enabled
        self.api_key = api_key
        self.voice_id = voice_id
        self.model_id = model_id
        self.output_format = output_format
        self.stability = stability
        self.similarity_boost = similarity_boost
        self.style = style
        self.speaker_boost = speaker_boost
        self.timeout = timeout
        self.enable_streaming = enable_streaming
        self.enable_async = enable_async
        
        # Stats
        self._stats = {
            "synthesized": 0,
            "total_chars": 0,
            "total_time_sec": 0.0,
            "errors": 0,
        }
    
    def stream(self, text: str) -> Iterator[bytes]:
        """
        Stream audio bytes from ElevenLabs TTS.
        
        Args:
            text: Text to synthesize
        
        Yields:
            PCM16 or MP3 audio chunks
        """
        if not self.enabled:
            return iter([])  # Empty iterator when disabled
        
        if not self.enable_streaming:
            # Non-streaming mode: synthesize all at once
            wav = self.synthesize_wav(text)
            yield wav
            return
        
        start_time = time.time()
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        params = {"output_format": self.output_format}
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "style": self.style,
                "use_speaker_boost": self.speaker_boost,
            },
        }
        
        try:
            with requests.post(
                url,
                headers=headers,
                params=params,
                json=payload,
                stream=True,
                timeout=self.timeout
            ) as r:
                r.raise_for_status()
                
                for chunk in r.iter_content(chunk_size=4096):
                    if chunk:
                        yield chunk
            
            # Update stats
            processing_time = time.time() - start_time
            self._stats["synthesized"] += 1
            self._stats["total_chars"] += len(text)
            self._stats["total_time_sec"] += processing_time
        
        except Exception as e:
            self._stats["errors"] += 1
            print(f"[TTS] Streaming error: {e}")
            raise
    
    async def stream_async(self, text: str) -> AsyncIterator[bytes]:
        """
        Async streaming audio from ElevenLabs TTS.
        
        Args:
            text: Text to synthesize
        
        Yields:
            PCM16 or MP3 audio chunks
        """
        if not self.enabled:
            return
        
        if not self.enable_streaming:
            wav = await self.synthesize_wav_async(text)
            yield wav
            return
        
        start_time = time.time()
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}/stream"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
        }
        params = {"output_format": self.output_format}
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "style": self.style,
                "use_speaker_boost": self.speaker_boost,
            },
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, params=params, json=payload) as response:
                    response.raise_for_status()
                    
                    async for chunk in response.content.iter_chunked(4096):
                        if chunk:
                            yield chunk
            
            # Update stats
            processing_time = time.time() - start_time
            self._stats["synthesized"] += 1
            self._stats["total_chars"] += len(text)
            self._stats["total_time_sec"] += processing_time
        
        except Exception as e:
            self._stats["errors"] += 1
            print(f"[TTS] Async streaming error: {e}")
            raise
    
    def synthesize_wav(self, text: str) -> bytes:
        """
        Non-streaming synthesis (fallback).
        
        Args:
            text: Text to synthesize
        
        Returns:
            Complete WAV audio bytes
        """
        if not self.enabled:
            return b""
        
        start_time = time.time()
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/wav"
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "style": self.style,
                "use_speaker_boost": self.speaker_boost,
            },
        }
        
        try:
            r = requests.post(url, headers=headers, json=payload, timeout=self.timeout)
            r.raise_for_status()
            
            # Update stats
            processing_time = time.time() - start_time
            self._stats["synthesized"] += 1
            self._stats["total_chars"] += len(text)
            self._stats["total_time_sec"] += processing_time
            
            return r.content
        
        except Exception as e:
            self._stats["errors"] += 1
            print(f"[TTS] Synthesis error: {e}")
            raise
    
    async def synthesize_wav_async(self, text: str) -> bytes:
        """
        Async non-streaming synthesis.
        
        Args:
            text: Text to synthesize
        
        Returns:
            Complete WAV audio bytes
        """
        if not self.enabled:
            return b""
        
        start_time = time.time()
        
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/wav"
        }
        payload = {
            "text": text,
            "model_id": self.model_id,
            "voice_settings": {
                "stability": self.stability,
                "similarity_boost": self.similarity_boost,
                "style": self.style,
                "use_speaker_boost": self.speaker_boost,
            },
        }
        
        try:
            timeout = aiohttp.ClientTimeout(total=self.timeout)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, headers=headers, json=payload) as response:
                    response.raise_for_status()
                    content = await response.read()
                    
                    # Update stats
                    processing_time = time.time() - start_time
                    self._stats["synthesized"] += 1
                    self._stats["total_chars"] += len(text)
                    self._stats["total_time_sec"] += processing_time
                    
                    return content
        
        except Exception as e:
            self._stats["errors"] += 1
            print(f"[TTS] Async synthesis error: {e}")
            raise
    
    def get_stats(self) -> dict:
        """Return TTS statistics."""
        stats = self._stats.copy()
        if stats["synthesized"] > 0:
            stats["avg_time_sec"] = stats["total_time_sec"] / stats["synthesized"]
            stats["avg_chars"] = stats["total_chars"] / stats["synthesized"]
        return stats
    
    def reset_stats(self):
        """Reset statistics."""
        self._stats = {
            "synthesized": 0,
            "total_chars": 0,
            "total_time_sec": 0.0,
            "errors": 0,
        }
    
    def get_config(self) -> dict:
        """Return current configuration."""
        return {
            "enabled": self.enabled,
            "voice_id": self.voice_id,
            "model_id": self.model_id,
            "output_format": self.output_format,
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "style": self.style,
            "speaker_boost": self.speaker_boost,
            "timeout": self.timeout,
            "enable_streaming": self.enable_streaming,
            "enable_async": self.enable_async,
        }
