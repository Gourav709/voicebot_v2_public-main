#!/usr/bin/env python3
"""
TTS Output Test
Tests ElevenLabs TTS and audio playback
"""
import os
from dotenv import load_dotenv
import sounddevice as sd

# Load environment
load_dotenv()

print("🔊 TTS Test Tool")
print("=" * 50)

# Check TTS settings
print("\n1. Checking .env configuration:")
enable_tts = os.getenv("ENABLE_TTS", "1")
api_key = os.getenv("ELEVENLABS_API_KEY", "")
voice_id = os.getenv("ELEVENLABS_VOICE_ID", "")
streaming = os.getenv("ELEVENLABS_STREAMING", "1")
output_format = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_16000")

print(f"   ENABLE_TTS: {enable_tts}")
print(f"   ELEVENLABS_API_KEY: {'✓ Set' if api_key else '✗ Missing'}")
print(f"   ELEVENLABS_VOICE_ID: {'✓ Set' if voice_id else '✗ Missing'}")
print(f"   ELEVENLABS_STREAMING: {streaming}")
print(f"   ELEVENLABS_OUTPUT_FORMAT: {output_format}")

if enable_tts != "1":
    print("\n⚠️  TTS is DISABLED in .env!")
    print("   Set ENABLE_TTS=1 to enable")
    exit()

if not api_key or not voice_id:
    print("\n⚠️  Missing ElevenLabs credentials!")
    print("   Set ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID in .env")
    exit()

# Test TTS
print("\n2. Testing ElevenLabs TTS...")
try:
    from src.providers.tts_elevenlabs import ElevenLabsTTS
    
    tts = ElevenLabsTTS(
        enabled=True,
        api_key=api_key,
        voice_id=voice_id,
        model_id=os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5"),
        output_format=output_format,
        stability=float(os.getenv("ELEVENLABS_STABILITY", "0.35")),
        similarity_boost=float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.8")),
        style=float(os.getenv("ELEVENLABS_STYLE", "0.0")),
        speaker_boost=os.getenv("ELEVENLABS_SPEAKER_BOOST", "1") == "1",
        timeout=60.0,
        enable_streaming=streaming == "1",
        enable_async=False,  # Use sync for testing
    )
    
    print("   ✓ TTS initialized successfully")
    
    # Generate short audio
    print("\n3. Generating test audio...")
    test_text = "Hello! This is a test. Can you hear me?"
    
    if streaming == "1":
        print("   Using streaming mode...")
        chunks = list(tts.stream(test_text))
        print(f"   ✓ Generated {len(chunks)} audio chunks")
        
        # Combine chunks
        audio_data = b''.join(chunks)
        print(f"   ✓ Total audio bytes: {len(audio_data)}")
    else:
        print("   Using non-streaming mode...")
        audio_data = tts.synthesize_wav(test_text)
        print(f"   ✓ Generated {len(audio_data)} bytes")
    
    # Play audio
    print("\n4. Playing audio...")
    print("   You should hear the test message now...")
    
    if output_format.startswith("pcm"):
        # PCM format - play directly
        import numpy as np
        
        # Convert bytes to int16 array
        audio_array = np.frombuffer(audio_data, dtype=np.int16)
        
        sd.play(audio_array, 16000)
        sd.wait()
        print("   ✓ Audio playback complete!")
    else:
        print("   ⚠️  Non-PCM format detected. May need decoding.")
        print("   Set ELEVENLABS_OUTPUT_FORMAT=pcm_16000 in .env")
    
    print("\n✓ TTS test completed successfully!")
    print("\nIf you heard the test message, TTS is working.")
    print("If not, check:")
    print("  1. System audio output device")
    print("  2. Audio permissions (macOS)")
    print("  3. sounddevice configuration")
    
except Exception as e:
    print(f"\n✗ Error during TTS test: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 50)
