#!/usr/bin/env python3
"""
Audio Output Diagnostic Tool
Tests if your system can play audio through sounddevice
"""
import numpy as np
import sounddevice as sd

print("🔊 Audio Output Diagnostic Tool")
print("=" * 50)

# Test 1: List audio devices
print("\n1. Available Audio Devices:")
print(sd.query_devices())

# Test 2: Get default output device
print("\n2. Default Output Device:")
try:
    default_device = sd.default.device[1]
    device_info = sd.query_devices(default_device)
    print(f"   Device: {device_info['name']}")
    print(f"   Channels: {device_info['max_output_channels']}")
    print(f"   Sample Rate: {device_info['default_samplerate']}")
except Exception as e:
    print(f"   Error: {e}")

# Test 3: Play a test tone
print("\n3. Playing 1-second test tone (440 Hz beep)...")
print("   You should hear a beep now...")
try:
    duration = 1.0
    sample_rate = 16000
    frequency = 440  # A4 note
    
    t = np.linspace(0, duration, int(sample_rate * duration))
    tone = np.sin(2 * np.pi * frequency * t) * 0.3
    tone_int16 = (tone * 32767).astype(np.int16)
    
    sd.play(tone_int16, sample_rate)
    sd.wait()
    
    print("   ✓ Test tone played successfully!")
    print("   Did you hear it? (Y/N)")
    
except Exception as e:
    print(f"   ✗ Error playing tone: {e}")

# Test 4: Check sounddevice configuration
print("\n4. Sounddevice Configuration:")
print(f"   Default device: {sd.default.device}")
print(f"   Default samplerate: {sd.default.samplerate}")
print(f"   Default channels: {sd.default.channels}")

print("\n" + "=" * 50)
print("Diagnostic complete!")
print("\nIf you didn't hear the test tone:")
print("1. Check system audio output device selection")
print("2. Check if other apps can play audio")
print("3. Try running with sudo (macOS permission issue)")
print("4. Check if headphones/speakers are connected")
