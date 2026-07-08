"""
Run this directly: python test_filler_audio.py
Tests filler audio independently of the bot to isolate the issue.
"""
import sys
import time
import numpy as np
import sounddevice as sd

print(f"sounddevice version: {sd.__version__}")
print(f"\nDefault output device: {sd.query_devices(kind='output')['name']}")
print(f"Default output latency: {sd.query_devices(kind='output')['default_low_output_latency']*1000:.1f}ms (low) / {sd.query_devices(kind='output')['default_high_output_latency']*1000:.1f}ms (high)")
print()

SAMPLE_RATE = 16000

# Test 1: Generate a simple 500ms beep and play it blocking
print("Test 1: Playing a 500ms 440Hz beep (blocking)...")
t = np.linspace(0, 0.5, int(SAMPLE_RATE * 0.5), dtype=np.float32)
beep = (np.sin(2 * np.pi * 440 * t) * 0.3 * 32767).astype(np.int16)
pcm = beep.tobytes()

stream = sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=1024)
stream.start()
stream.write(pcm)
time.sleep(0.6)  # wait for buffer to flush
stream.stop()
stream.close()
print("  Did you hear a beep? (should have heard one)")
print()

# Test 2: Same beep but abort() immediately after write — simulates what filler does
print("Test 2: Writing beep then immediately abort() — simulates premature stop...")
stream = sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=1024)
stream.start()
stream.write(pcm)
stream.abort()  # cut immediately after write
stream.close()
print("  Did you hear anything? (probably not — this is the bug)")
print()

# Test 3: Write beep, wait for latency, then stop()
latency_ms = sd.query_devices(kind='output')['default_high_output_latency'] * 1000
wait_s = (latency_ms + 200) / 1000  # latency + 200ms buffer drain time
print(f"Test 3: Writing beep, waiting {wait_s*1000:.0f}ms for buffer drain, then stop()...")
stream = sd.RawOutputStream(samplerate=SAMPLE_RATE, channels=1, dtype='int16', blocksize=1024)
stream.start()
stream.write(pcm)
time.sleep(wait_s)
stream.stop()
stream.close()
print("  Did you hear a beep? (should have with drain wait)")
print()

print("Results tell us what the fix needs to be.")