"""
Audio Denoising Module
Provides multiple denoising strategies for cleaning incoming audio.
All denoising is configurable via environment variables.
"""
import numpy as np
from typing import Optional
from enum import Enum

class DenoiserType(Enum):
    NONE = "none"
    NOISEREDUCE = "noisereduce"
    SPECTRAL = "spectral"
    WIENER = "wiener"


class AudioDenoiser:
    """
    Modular audio denoiser with multiple strategies.
    All parameters controlled via .env file.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        denoiser_type: str = "noisereduce",
        strength: float = 0.7,
        stationary: bool = True,
        sample_rate: int = 16000,
    ):
        self.enabled = enabled
        self.denoiser_type = DenoiserType(denoiser_type.lower())
        self.strength = max(0.0, min(1.0, strength))
        self.stationary = stationary
        self.sample_rate = sample_rate
        
        # Import heavy libraries only if needed
        self._noisereduce = None
        self._scipy = None
        
        if self.enabled and self.denoiser_type != DenoiserType.NONE:
            self._initialize_backend()
    
    def _initialize_backend(self):
        """Lazy load denoising libraries based on type."""
        if self.denoiser_type == DenoiserType.NOISEREDUCE:
            try:
                import noisereduce as nr
                self._noisereduce = nr
            except ImportError:
                raise RuntimeError(
                    "noisereduce not installed. Run: pip install noisereduce scipy"
                )
        
        elif self.denoiser_type in (DenoiserType.SPECTRAL, DenoiserType.WIENER):
            try:
                import scipy.signal
                self._scipy = scipy
            except ImportError:
                raise RuntimeError(
                    "scipy not installed. Run: pip install scipy"
                )
    
    def denoise(self, audio: np.ndarray) -> np.ndarray:
        """
        Denoise audio using selected strategy.
        
        Args:
            audio: Float32 numpy array (-1.0 to 1.0)
        
        Returns:
            Denoised audio (same shape and dtype)
        """
        if not self.enabled or self.denoiser_type == DenoiserType.NONE:
            return audio
        
        if audio.size == 0:
            return audio
        
        if self.denoiser_type == DenoiserType.NOISEREDUCE:
            return self._denoise_noisereduce(audio)
        elif self.denoiser_type == DenoiserType.SPECTRAL:
            return self._denoise_spectral(audio)
        elif self.denoiser_type == DenoiserType.WIENER:
            return self._denoise_wiener(audio)
        
        return audio
    
    def denoise_pcm16(self, pcm16: bytes) -> bytes:
        """
        Denoise PCM16 audio bytes.
        
        Args:
            pcm16: Raw PCM16 bytes (int16 mono)
        
        Returns:
            Denoised PCM16 bytes
        """
        if not self.enabled or self.denoiser_type == DenoiserType.NONE:
            return pcm16
        
        # Convert to float32
        audio = np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0
        
        # Denoise
        denoised = self.denoise(audio)
        
        # Convert back to PCM16
        pcm16_out = (np.clip(denoised, -1.0, 1.0) * 32767).astype(np.int16).tobytes()
        
        return pcm16_out
    
    def _denoise_noisereduce(self, audio: np.ndarray) -> np.ndarray:
        """
        Use noisereduce library (recommended for voice).
        
        Features:
        - Automatic noise profile estimation
        - Stationary and non-stationary noise handling
        - Preserves voice quality
        """
        try:
            # Adjust prop_decrease based on strength
            # strength 0.0 = no reduction, 1.0 = maximum reduction
            prop_decrease = self.strength
            
            denoised = self._noisereduce.reduce_noise(
                y=audio,
                sr=self.sample_rate,
                stationary=self.stationary,
                prop_decrease=prop_decrease,
            )
            
            return denoised.astype(np.float32)
        
        except Exception as e:
            # Fallback to original audio on error
            print(f"Denoising failed: {e}, returning original audio")
            return audio
    
    def _denoise_spectral(self, audio: np.ndarray) -> np.ndarray:
        """
        Spectral subtraction method.
        
        Features:
        - Fast and lightweight
        - Good for stationary noise
        - May introduce musical noise artifacts
        """
        if self._scipy is None:
            return audio
        
        try:
            from scipy.signal import stft, istft
            
            # STFT parameters
            nperseg = 512
            noverlap = nperseg // 2
            
            # Compute STFT
            f, t, Zxx = stft(audio, fs=self.sample_rate, nperseg=nperseg, noverlap=noverlap)
            
            # Estimate noise from first 0.5 seconds
            noise_frames = int(0.5 * self.sample_rate / (nperseg - noverlap))
            noise_frames = min(noise_frames, Zxx.shape[1] // 4)
            
            if noise_frames > 0:
                noise_magnitude = np.median(np.abs(Zxx[:, :noise_frames]), axis=1, keepdims=True)
                
                # Spectral subtraction
                magnitude = np.abs(Zxx)
                phase = np.angle(Zxx)
                
                # Subtract noise scaled by strength
                magnitude_clean = np.maximum(
                    magnitude - self.strength * noise_magnitude,
                    0.1 * magnitude  # Floor to avoid over-suppression
                )
                
                # Reconstruct
                Zxx_clean = magnitude_clean * np.exp(1j * phase)
                
                # Inverse STFT
                _, denoised = istft(Zxx_clean, fs=self.sample_rate, nperseg=nperseg, noverlap=noverlap)
                
                # Match original length
                if len(denoised) > len(audio):
                    denoised = denoised[:len(audio)]
                elif len(denoised) < len(audio):
                    denoised = np.pad(denoised, (0, len(audio) - len(denoised)))
                
                return denoised.astype(np.float32)
            
            return audio
        
        except Exception as e:
            print(f"Spectral denoising failed: {e}, returning original audio")
            return audio
    
    def _denoise_wiener(self, audio: np.ndarray) -> np.ndarray:
        """
        Wiener filtering method.
        
        Features:
        - Good balance of noise reduction and quality
        - Adaptive to signal characteristics
        - Lower artifacts than spectral subtraction
        """
        if self._scipy is None:
            return audio
        
        try:
            from scipy.signal import wiener
            
            # Wiener filter size based on strength
            # strength 0.0 → size 3, strength 1.0 → size 15
            mysize = int(3 + self.strength * 12)
            mysize = mysize if mysize % 2 == 1 else mysize + 1  # Must be odd
            
            denoised = wiener(audio, mysize=mysize)
            
            return denoised.astype(np.float32)
        
        except Exception as e:
            print(f"Wiener denoising failed: {e}, returning original audio")
            return audio
    
    def get_config(self) -> dict:
        """Return current configuration."""
        return {
            "enabled": self.enabled,
            "type": self.denoiser_type.value,
            "strength": self.strength,
            "stationary": self.stationary,
            "sample_rate": self.sample_rate,
        }


def create_denoiser_from_env(
    enabled: bool,
    denoiser_type: str,
    strength: float,
    stationary: bool,
    sample_rate: int,
) -> AudioDenoiser:
    """
    Factory function to create denoiser from environment variables.
    
    Usage:
        from os import getenv
        denoiser = create_denoiser_from_env(
            enabled=getenv("ENABLE_DENOISER", "1") == "1",
            denoiser_type=getenv("DENOISER_TYPE", "noisereduce"),
            strength=float(getenv("DENOISER_STRENGTH", "0.7")),
            stationary=getenv("DENOISER_STATIONARY", "1") == "1",
            sample_rate=int(getenv("SAMPLE_RATE", "16000")),
        )
    """
    return AudioDenoiser(
        enabled=enabled,
        denoiser_type=denoiser_type,
        strength=strength,
        stationary=stationary,
        sample_rate=sample_rate,
    )
