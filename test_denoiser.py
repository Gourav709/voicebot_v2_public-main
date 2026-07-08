"""
Records 4 seconds of audio, plays it back raw, then plays it through the denoiser.
Run: python test_denoiser.py
"""
import sys, time
import numpy as np
import sounddevice as sd

sys.path.insert(0, '.')
from src.providers.denoiser import AudioDenoiser

SR = 16000

print("=" * 50)
print("Recording 4 seconds — speak now...")
print("=" * 50)
audio = sd.rec(int(4 * SR), samplerate=SR, channels=1, dtype='float32')
sd.wait()
audio = audio[:, 0]  # mono
print(f"Recorded {len(audio)/SR:.1f}s  |  peak amplitude: {np.max(np.abs(audio)):.3f}")

# ── Playback 1: raw ──
print("\n▶  Playing RAW audio...")
sd.play(audio, SR)
sd.wait()
print("   Done.")

time.sleep(0.5)

# ── Playback 2: denoised ──
print("\n⚙  Running denoiser (noisereduce, strength=0.7)...")
try:
    denoiser = AudioDenoiser(
        enabled=True,
        denoiser_type="noisereduce",
        strength=0.7,
        stationary=True,
        sample_rate=SR,
    )
    denoised = denoiser.denoise(audio)
    print(f"   Done.  |  peak amplitude after: {np.max(np.abs(denoised)):.3f}")

    print("\n▶  Playing DENOISED audio...")
    sd.play(denoised, SR)
    sd.wait()
    print("   Done.")

except ImportError:
    print("   noisereduce not installed — run: pip install noisereduce")
    sys.exit(1)
except Exception as e:
    print(f"   Denoiser error: {e}")

print("\n✓ Test complete.")