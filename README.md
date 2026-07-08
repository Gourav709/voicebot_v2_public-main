# Voicebot V2 Enhanced - Modular Voice Assistant

🎯 **Enterprise-grade voice assistant with complete .env configurability**

## What's New in V2 Enhanced

### ✨ Key Improvements

1. **🔧 100% .env Configurable**
   - Every module can be enabled/disabled via environment variables
   - No code changes needed to adjust behavior
   - Perfect for testing, development, and production

2. **⚡ Async Support**
   - Optional async/await for all I/O operations
   - Better performance and responsiveness
   - Configurable via `ENABLE_ASYNC=1`

3. **🎵 Modular Audio Denoising**
   - Multiple denoising strategies (noisereduce, spectral, Wiener)
   - Adjustable strength and settings
   - Cleanses audio before STT processing
   - Enable/disable with `ENABLE_DENOISER=1`

4. **📊 Performance Monitoring**
   - Built-in statistics tracking
   - Real-time performance metrics
   - Session summaries on exit

5. **🛡️ Enhanced Error Handling**
   - Graceful fallbacks for all components
   - Configurable error behavior
   - Detailed error logging

---

## Quick Start

### Installation

```bash
# Clone or extract the project
cd voicebot_v2_enhanced

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure .env
cp .env.example .env
# Edit .env with your API keys
```

### Minimal Configuration

```bash
# Required API keys
GROQ_API_KEY=your_groq_api_key_here
ELEVENLABS_API_KEY=your_elevenlabs_api_key_here
ELEVENLABS_VOICE_ID=your_voice_id_here
```

### Run

```bash
python run_local_v2.py
```

---

## Complete .env Configuration Guide

### 🎤 Audio Settings

```bash
# Basic audio parameters
SAMPLE_RATE=16000                    # Audio sample rate (Hz)
VAD_AGGRESSIVENESS=2                 # Voice Activity Detection: 0 (least) to 3 (most aggressive)
FRAME_MS=20                          # Audio frame duration (milliseconds)
END_SILENCE_MS=800                   # Silence before stopping recording
MAX_UTTERANCE_SEC=20                 # Maximum recording duration
```

### 🛑 Barge-in Configuration

**Enable/disable barge-in (user can interrupt bot):**

```bash
ENABLE_BARGE_IN=1                    # 1=enabled, 0=disabled
BARGE_IN_TRIGGER_MS=120              # How long user must speak to interrupt
BARGE_IN_SENSITIVITY=2               # VAD sensitivity during playback (0-3)
```

**Use Cases:**
- `ENABLE_BARGE_IN=0`: Disable for presentations/announcements
- `BARGE_IN_TRIGGER_MS=50`: More responsive (may have false positives)
- `BARGE_IN_TRIGGER_MS=200`: More stable (less sensitive)

### 🎵 Audio Denoising

**Remove background noise from user audio:**

```bash
ENABLE_DENOISER=1                    # 1=enabled, 0=disabled
DENOISER_TYPE=noisereduce            # Options: noisereduce, spectral, wiener, none
DENOISER_STRENGTH=0.7                # 0.0 (no reduction) to 1.0 (max reduction)
DENOISER_STATIONARY=1                # 1=stationary noise (fan, AC), 0=non-stationary
```

**Denoiser Types:**
- `noisereduce`: Best quality, preserves voice (recommended)
- `spectral`: Fast, good for constant noise
- `wiener`: Balanced, minimal artifacts
- `none`: No denoising

**Use Cases:**
- Call center: `TYPE=noisereduce, STRENGTH=0.7, STATIONARY=1`
- Office environment: `TYPE=spectral, STRENGTH=0.5, STATIONARY=1`
- Mobile/outdoor: `TYPE=noisereduce, STRENGTH=0.8, STATIONARY=0`

### 🎯 STT Configuration

**Control speech-to-text behavior:**

```bash
ENABLE_STT=1                         # 1=enabled, 0=disabled (for testing)
WHISPER_MODEL=small                  # Model size: tiny, base, small, medium, large
WHISPER_DEVICE=cpu                   # Device: cpu or cuda
WHISPER_COMPUTE_TYPE=int8            # Precision: int8, int16, float16, float32
WHISPER_LANGUAGE=en                  # Language hint (or leave empty for auto-detect)
WHISPER_VAD_FILTER=0                 # Use Whisper's internal VAD
WHISPER_BEAM_SIZE=5                  # Beam search size (1-10, higher=better quality, slower)
```

**Model Selection:**
- `tiny`: Fastest, less accurate (~1GB RAM)
- `small`: Balanced (recommended, ~2GB RAM)
- `medium`: Better accuracy (~5GB RAM)
- `large`: Best accuracy (~10GB RAM)

**Compute Type:**
- `int8`: Fastest, lowest quality, minimal RAM
- `float16`: Good balance (requires CUDA)
- `float32`: Best quality, slower

### 🤖 LLM Configuration

**Control language model behavior:**

```bash
ENABLE_LLM=1                         # 1=enabled, 0=disabled (for testing)
GROQ_API_KEY=your_key                # Required if enabled
GROQ_MODEL=llama-3.3-70b-versatile   # Model name
GROQ_TEMPERATURE=0.2                 # 0.0 (deterministic) to 2.0 (creative)
GROQ_MAX_TOKENS=350                  # Max response tokens
GROQ_TIMEOUT=60                      # API timeout (seconds)
GROQ_MAX_RETRIES=2                   # Retry attempts on failure
```

**Temperature Guide:**
- `0.0-0.3`: Consistent, script-like responses (recommended)
- `0.4-0.7`: Balanced creativity
- `0.8-1.0`: More varied responses

### 🔊 TTS Configuration

**Control text-to-speech output:**

```bash
ENABLE_TTS=1                         # 1=enabled, 0=disabled (for testing)
ELEVENLABS_API_KEY=your_key          # Required if enabled
ELEVENLABS_VOICE_ID=your_voice_id    # Voice ID from ElevenLabs
ELEVENLABS_MODEL_ID=eleven_turbo_v2_5
ELEVENLABS_OUTPUT_FORMAT=pcm_16000   # Format: pcm_16000, mp3_44100_128
ELEVENLABS_STABILITY=0.35            # 0.0 (variable) to 1.0 (stable)
ELEVENLABS_SIMILARITY_BOOST=0.8      # 0.0 to 1.0 (voice similarity)
ELEVENLABS_STYLE=0.0                 # 0.0 to 1.0 (style exaggeration)
ELEVENLABS_SPEAKER_BOOST=1           # Enhance speaker clarity
ELEVENLABS_TIMEOUT=60                # API timeout
ELEVENLABS_STREAMING=1               # 1=streaming (low latency), 0=batch
```

**Voice Settings:**
- High stability (0.7-1.0): Consistent, professional
- Low stability (0.0-0.3): More expressive, varied
- Similarity boost: Higher = closer to original voice

### ⚡ Performance Settings

```bash
ENABLE_ASYNC=1                       # 1=async mode, 0=sync mode
ASYNC_QUEUE_SIZE=10                  # Max items in async queues
ASYNC_TIMEOUT=30                     # Timeout for async operations
USE_THREADING=1                      # Use threads for I/O operations
BUFFER_SIZE=4096                     # Audio buffer size
ENABLE_PROFILING=0                   # Log performance metrics
```

### 📝 Logging Configuration

```bash
LOG_EVENTS_TO_FILE=1                 # Save events to file
EVENTS_FILE=./logs/events.jsonl      # Event log path
LOG_LEVEL=INFO                       # DEBUG, INFO, WARNING, ERROR
LOG_AUDIO_STATS=1                    # Log audio statistics
SAVE_AUDIO_FILES=0                   # Save audio for debugging
AUDIO_DEBUG_PATH=./logs/audio_debug/
```

### 🛡️ Error Handling

**Configure fallback behavior on errors:**

```bash
FALLBACK_ON_STT_ERROR=1              # Continue with empty text on STT error
FALLBACK_ON_LLM_ERROR=1              # Use handoff script on LLM error
FALLBACK_ON_TTS_ERROR=1              # Skip playback on TTS error
```

---

## Common Configuration Scenarios

### 1. Production Call Center

```bash
# High quality, robust
ENABLE_BARGE_IN=1
BARGE_IN_TRIGGER_MS=150
ENABLE_DENOISER=1
DENOISER_TYPE=noisereduce
DENOISER_STRENGTH=0.7
WHISPER_MODEL=small
ENABLE_ASYNC=1
LOG_EVENTS_TO_FILE=1
LOG_AUDIO_STATS=1
```

### 2. Development/Testing

```bash
# Fast iteration, detailed logging
ENABLE_BARGE_IN=1
ENABLE_DENOISER=0                    # Faster without denoising
WHISPER_MODEL=tiny                   # Fastest model
ENABLE_ASYNC=0                       # Easier debugging
LOG_LEVEL=DEBUG
LOG_AUDIO_STATS=1
SAVE_AUDIO_FILES=1                   # Save audio for analysis
```

### 3. Low-Resource Environment

```bash
# Minimal resource usage
ENABLE_BARGE_IN=0                    # Save CPU
ENABLE_DENOISER=0
WHISPER_MODEL=tiny
WHISPER_COMPUTE_TYPE=int8
ENABLE_ASYNC=0
ELEVENLABS_STREAMING=0               # Batch mode
```

### 4. High-Quality Demo

```bash
# Best quality, all features
ENABLE_BARGE_IN=1
BARGE_IN_TRIGGER_MS=100
ENABLE_DENOISER=1
DENOISER_TYPE=noisereduce
DENOISER_STRENGTH=0.8
WHISPER_MODEL=medium
WHISPER_BEAM_SIZE=7
GROQ_TEMPERATURE=0.1
ELEVENLABS_STABILITY=0.5
ENABLE_ASYNC=1
```

### 5. Testing Individual Components

**Test STT only:**
```bash
ENABLE_STT=1
ENABLE_LLM=0
ENABLE_TTS=0
```

**Test LLM only:**
```bash
ENABLE_STT=0
ENABLE_LLM=1
ENABLE_TTS=0
```

**Test TTS only:**
```bash
ENABLE_STT=0
ENABLE_LLM=0
ENABLE_TTS=1
```

---

## Audio Denoising Deep Dive

### When to Use Denoising

✅ **Use denoising when:**
- Call center environments (background chatter)
- Home office (keyboard, fan noise)
- Mobile/outdoor settings
- Low-quality microphones
- Multiple speakers in room

❌ **Skip denoising when:**
- Studio-quality microphones
- Quiet environments
- Need maximum speed
- Testing/development

### Denoiser Comparison

| Type | Speed | Quality | Best For |
|------|-------|---------|----------|
| `noisereduce` | Moderate | Excellent | Voice quality preservation |
| `spectral` | Fast | Good | Constant background noise |
| `wiener` | Moderate | Very Good | Balanced reduction |
| `none` | Instant | N/A | Clean environments |

### Tuning Strength

```bash
DENOISER_STRENGTH=0.3   # Light reduction, preserve voice character
DENOISER_STRENGTH=0.7   # Balanced (recommended)
DENOISER_STRENGTH=0.9   # Aggressive, may affect voice quality
```

---

## Barge-in Configuration

### Sensitivity vs. Responsiveness

```bash
# Very responsive (may have false triggers)
BARGE_IN_TRIGGER_MS=50
BARGE_IN_SENSITIVITY=1

# Balanced (recommended)
BARGE_IN_TRIGGER_MS=120
BARGE_IN_SENSITIVITY=2

# Very stable (less responsive)
BARGE_IN_TRIGGER_MS=250
BARGE_IN_SENSITIVITY=3
```

### Disabling Barge-in

**When to disable:**
- Playing important announcements
- Emergency notifications
- Legal disclaimers
- Non-interactive scenarios

```bash
ENABLE_BARGE_IN=0
```

---

## Performance Tuning

### Latency Optimization

**Minimize time to first audio:**

```bash
# Use async for parallel processing
ENABLE_ASYNC=1

# Use streaming TTS
ELEVENLABS_STREAMING=1

# Faster STT model
WHISPER_MODEL=tiny

# Skip denoising
ENABLE_DENOISER=0

# Result: ~1-1.5 second latency
```

### Accuracy Optimization

**Maximize transcription and response quality:**

```bash
# Better STT
WHISPER_MODEL=medium
WHISPER_BEAM_SIZE=7

# Clean audio
ENABLE_DENOISER=1
DENOISER_TYPE=noisereduce
DENOISER_STRENGTH=0.7

# More deterministic LLM
GROQ_TEMPERATURE=0.1

# Result: Higher quality, ~2-3 second latency
```

### Resource Optimization

**Run on low-spec hardware:**

```bash
WHISPER_MODEL=tiny
WHISPER_COMPUTE_TYPE=int8
ENABLE_DENOISER=0
ENABLE_ASYNC=0
BUFFER_SIZE=2048
```

---

## Monitoring & Debugging

### Session Statistics

The bot displays statistics on exit (Ctrl+C):

```
📊 Session Statistics
  Audio: 15 recordings, 3 barge-ins, 12 denoised
  STT: 15 transcriptions, RTF: 0.35x
  LLM: 15 completions, 4500 tokens, 0 retries
  TTS: 15 synthesized, 2100 chars
```

### Metrics Explained

- **RTF (Real-Time Factor)**: Processing time / audio duration
  - < 1.0: Faster than real-time ✓
  - > 1.0: Slower than real-time ⚠️
  
- **Barge-ins**: How often users interrupted
  - High count: May indicate slow responses or trigger sensitivity

- **Retries**: LLM API retry count
  - > 0: Network issues or rate limiting

### Debug Logging

```bash
# Enable detailed logging
LOG_LEVEL=DEBUG
LOG_AUDIO_STATS=1
SAVE_AUDIO_FILES=1
```

Check `./logs/events.jsonl` for:
- User text
- LLM plans
- Script assembly
- Errors

---

## Troubleshooting

### Common Issues

**1. "Barge-in triggers too often"**
```bash
BARGE_IN_TRIGGER_MS=200  # Increase threshold
BARGE_IN_SENSITIVITY=3   # More conservative
```

**2. "Poor transcription accuracy"**
```bash
ENABLE_DENOISER=1        # Clean audio first
WHISPER_MODEL=medium     # Better model
WHISPER_BEAM_SIZE=7      # More thorough search
```

**3. "Too much latency"**
```bash
WHISPER_MODEL=tiny       # Faster STT
ENABLE_DENOISER=0        # Skip denoising
ELEVENLABS_STREAMING=1   # Stream TTS
ENABLE_ASYNC=1           # Parallel processing
```

**4. "Denoising makes voice sound robotic"**
```bash
DENOISER_STRENGTH=0.5    # Reduce strength
DENOISER_TYPE=wiener     # Try different algorithm
```

**5. "High CPU usage"**
```bash
WHISPER_MODEL=tiny
ENABLE_DENOISER=0
ENABLE_ASYNC=0
```

---

## Architecture

### Component Overview

```
User Speech
    ↓
[VAD Detection] ← ENABLE_BARGE_IN
    ↓
[Record Audio]
    ↓
[Denoising] ← ENABLE_DENOISER, DENOISER_TYPE
    ↓
[STT] ← ENABLE_STT, WHISPER_MODEL
    ↓
[LLM Planning] ← ENABLE_LLM, GROQ_MODEL
    ↓
[Script Assembly]
    ↓
[TTS] ← ENABLE_TTS, ELEVENLABS_STREAMING
    ↓
[Audio Playback] ← ENABLE_BARGE_IN (monitoring)
```

### Module Responsibilities

- **AudioIO**: Recording, playback, barge-in monitoring
- **Denoiser**: Audio noise reduction
- **STT**: Speech-to-text conversion
- **LLM**: Intent classification and planning
- **ScriptController**: Response assembly
- **TTS**: Text-to-speech synthesis

---

## API Keys Setup

### Groq (LLM)

1. Visit https://console.groq.com
2. Sign up / Log in
3. Create API key
4. Add to `.env`: `GROQ_API_KEY=your_key`

### ElevenLabs (TTS)

1. Visit https://elevenlabs.io
2. Sign up / Log in
3. Get API key from profile
4. Get Voice ID from voices page
5. Add to `.env`:
   ```bash
   ELEVENLABS_API_KEY=your_key
   ELEVENLABS_VOICE_ID=voice_id
   ```

---

## Advanced Usage

### Custom Denoiser

Want to add a new denoiser? Edit `src/providers/denoiser.py`:

```python
def _denoise_custom(self, audio: np.ndarray) -> np.ndarray:
    # Your denoising algorithm here
    return denoised_audio
```

Then use:
```bash
DENOISER_TYPE=custom
```

### Async Event Loop

The bot automatically uses async when enabled, but you can also run in async context:

```python
import asyncio
from src.app.main import run

asyncio.run(run())
```

---

## License

[Your License Here]

## Support

For issues or questions, please file an issue on the repository.

---

**Happy Building! 🎉**
