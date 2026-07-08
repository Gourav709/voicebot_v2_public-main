"""
Enhanced Voicebot V2 Main Application
All modules configurable via .env file
Includes transcript and analytics support

STT providers: whisper (local) | deepgram (cloud)
TTS providers: elevenlabs | sarvam
Switch via STT_PROVIDER and TTS_PROVIDER in .env
"""
import os
import sys
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

from src.core.orchestrator import OrchestratorV2
from src.context.customer_context import CustomerContextStore
from src.faq.store import FAQStore
from src.core.logger import EventLogger

from src.providers.audio_io import AudioIO
from src.providers.stt_faster_whisper import FasterWhisperSTT
from src.providers.llm_groq import GroqLLM
from src.providers.tts_elevenlabs import ElevenLabsTTS
from src.providers.denoiser import create_denoiser_from_env

from src.analytics.transcript import create_transcript_from_env
from src.analytics.analytics import create_analytics_from_env
from src.core.filler import FillerManager

console = Console()


def load_config():
    """Load all configuration from .env file."""
    load_dotenv()

    config = {
        # Data files
        "customers_csv": os.getenv("CUSTOMERS_CSV", "./data/customers.csv"),
        "faqs_json": os.getenv("FAQS_JSON", "./data/faqs.json"),
        "knowledge_mode": os.getenv("KNOWLEDGE_MODE", "faq").lower(),
        "system_prompt": os.getenv("SYSTEM_PROMPT", "./config/prompts/system_prompt.txt"),
        "greeting_prompt": os.getenv("GREETING_PROMPT", "./config/prompts/greeting.txt"),
        "llm_max_words": int(os.getenv("LLM_MAX_WORDS", "50")),
        "llm_context_turns": int(os.getenv("LLM_CONTEXT_TURNS", "5")),
        "llm_summarise_every": int(os.getenv("LLM_SUMMARISE_EVERY", "3")),
        "silence_timeout_sec": int(os.getenv("SILENCE_TIMEOUT_SEC", "8")),
        "silence_max_prompts": int(os.getenv("SILENCE_MAX_PROMPTS", "2")),
        "llm_tts_streaming": os.getenv("LLM_TTS_STREAMING", "0") == "1",
        "llm_json_instructions": os.getenv("LLM_JSON_INSTRUCTIONS", "./config/prompts/llm_json_instructions.txt"),

        # Customer lookup
        "lookup_key": os.getenv("CUSTOMER_LOOKUP_KEY", "MOBILENO"),
        "lookup_val": os.getenv("CUSTOMER_LOOKUP_VALUE", "").strip(),

        # Audio settings
        "sample_rate": int(os.getenv("SAMPLE_RATE", "16000")),
        "vad_aggr": int(os.getenv("VAD_AGGRESSIVENESS", "2")),
        "frame_ms": int(os.getenv("FRAME_MS", "20")),
        "end_silence_ms": int(os.getenv("END_SILENCE_MS", "800")),
        "max_utt_sec": int(os.getenv("MAX_UTTERANCE_SEC", "20")),

        # Barge-in
        "enable_barge_in": os.getenv("ENABLE_BARGE_IN", "1") == "1",
        "barge_in_trigger_ms": int(os.getenv("BARGE_IN_TRIGGER_MS", "120")),
        "barge_in_sensitivity": int(os.getenv("BARGE_IN_SENSITIVITY", "2")),

        # Denoiser
        "enable_denoiser": os.getenv("ENABLE_DENOISER", "1") == "1",
        "denoiser_type": os.getenv("DENOISER_TYPE", "noisereduce"),
        "denoiser_strength": float(os.getenv("DENOISER_STRENGTH", "0.7")),
        "denoiser_stationary": os.getenv("DENOISER_STATIONARY", "1") == "1",

        # ── STT provider selection ──────────────────────────────────────────
        # STT_PROVIDER=whisper  → use local Faster-Whisper (default)
        # STT_PROVIDER=deepgram → use Deepgram cloud API
        "stt_provider": os.getenv("STT_PROVIDER", "whisper").lower(),
        "enable_stt": os.getenv("ENABLE_STT", "1") == "1",

        # Whisper-specific
        "whisper_model": os.getenv("WHISPER_MODEL", "small"),
        "whisper_device": os.getenv("WHISPER_DEVICE", "cpu"),
        "whisper_compute_type": os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
        "whisper_language": os.getenv("WHISPER_LANGUAGE", "en") if os.getenv("WHISPER_LANGUAGE") else None,
        "whisper_vad_filter": os.getenv("WHISPER_VAD_FILTER", "0") == "1",
        "whisper_beam_size": int(os.getenv("WHISPER_BEAM_SIZE", "5")),

        # Deepgram-specific
        "deepgram_api_key": os.getenv("DEEPGRAM_API_KEY", ""),
        "deepgram_stt_mode": os.getenv("DEEPGRAM_STT_MODE", "batch"),
        "deepgram_model": os.getenv("DEEPGRAM_MODEL", "nova-2"),
        "deepgram_language": os.getenv("DEEPGRAM_LANGUAGE", "en-IN"),
        "deepgram_punctuate": os.getenv("DEEPGRAM_PUNCTUATE", "1") == "1",
        "deepgram_smart_format": os.getenv("DEEPGRAM_SMART_FORMAT", "1") == "1",
        "deepgram_multilingual": os.getenv("DEEPGRAM_MULTILINGUAL", "1") == "1",
        "deepgram_timeout": float(os.getenv("DEEPGRAM_TIMEOUT", "15")),
        "deepgram_endpointing_ms": int(os.getenv("DEEPGRAM_ENDPOINTING_MS", "300")),
        "deepgram_utterance_end_ms": int(os.getenv("DEEPGRAM_UTTERANCE_END_MS", "1000")),

        # LLM
        "enable_llm": os.getenv("ENABLE_LLM", "1") == "1",
        "groq_api_key": os.getenv("GROQ_API_KEY", ""),
        "groq_model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        "groq_temperature": float(os.getenv("GROQ_TEMPERATURE", "0.4")),
        "groq_max_tokens": int(os.getenv("GROQ_MAX_TOKENS", "200")),
        "groq_timeout": float(os.getenv("GROQ_TIMEOUT", "60")),
        "groq_max_retries": int(os.getenv("GROQ_MAX_RETRIES", "2")),

        # ── TTS provider selection ──────────────────────────────────────────
        # TTS_PROVIDER=elevenlabs → use ElevenLabs (default)
        # TTS_PROVIDER=sarvam     → use Sarvam AI (Indian voices / Hinglish)
        "tts_provider": os.getenv("TTS_PROVIDER", "elevenlabs").lower(),
        "enable_tts": os.getenv("ENABLE_TTS", "1") == "1",

        # ElevenLabs-specific
        "elevenlabs_api_key": os.getenv("ELEVENLABS_API_KEY", ""),
        "elevenlabs_voice_id": os.getenv("ELEVENLABS_VOICE_ID", ""),
        "elevenlabs_model_id": os.getenv("ELEVENLABS_MODEL_ID", "eleven_turbo_v2_5"),
        "elevenlabs_output_format": os.getenv("ELEVENLABS_OUTPUT_FORMAT", "pcm_16000"),
        "elevenlabs_stability": float(os.getenv("ELEVENLABS_STABILITY", "0.45")),
        "elevenlabs_similarity_boost": float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.75")),
        "elevenlabs_style": float(os.getenv("ELEVENLABS_STYLE", "0.30")),
        "elevenlabs_speaker_boost": os.getenv("ELEVENLABS_SPEAKER_BOOST", "1") == "1",
        "elevenlabs_timeout": float(os.getenv("ELEVENLABS_TIMEOUT", "60")),
        "elevenlabs_streaming": os.getenv("ELEVENLABS_STREAMING", "1") == "1",

        # Sarvam-specific
        "sarvam_api_key": os.getenv("SARVAM_API_KEY", ""),
        "sarvam_model": os.getenv("SARVAM_MODEL", "bulbul:v2"),
        "sarvam_speaker": os.getenv("SARVAM_SPEAKER", "anushka"),
        "sarvam_language": os.getenv("SARVAM_LANGUAGE", "en-IN"),
        "sarvam_pitch": float(os.getenv("SARVAM_PITCH", "0.0")),
        "sarvam_pace": float(os.getenv("SARVAM_PACE", "1.1")),
        "sarvam_loudness": float(os.getenv("SARVAM_LOUDNESS", "1.5")),
        "sarvam_temperature": float(os.getenv("SARVAM_TEMPERATURE", "0.6")),
        "sarvam_timeout": float(os.getenv("SARVAM_TIMEOUT", "20")),

        # Async
        "enable_async": os.getenv("ENABLE_ASYNC", "1") == "1",
        "async_queue_size": int(os.getenv("ASYNC_QUEUE_SIZE", "10")),
        "async_timeout": float(os.getenv("ASYNC_TIMEOUT", "30")),

        # Performance
        "use_threading": os.getenv("USE_THREADING", "1") == "1",
        "buffer_size": int(os.getenv("BUFFER_SIZE", "4096")),
        "enable_profiling": os.getenv("ENABLE_PROFILING", "0") == "1",

        # Logging
        "log_events_to_file": os.getenv("LOG_EVENTS_TO_FILE", "1") == "1",
        "events_file": os.getenv("EVENTS_FILE", "./logs/events.jsonl"),
        "log_level": os.getenv("LOG_LEVEL", "INFO"),
        "log_audio_stats": os.getenv("LOG_AUDIO_STATS", "0") == "1",
        "save_audio_files": os.getenv("SAVE_AUDIO_FILES", "0") == "1",
        "audio_debug_path": os.getenv("AUDIO_DEBUG_PATH", "./logs/audio_debug/"),

        # Fallbacks
        "fallback_on_stt_error": os.getenv("FALLBACK_ON_STT_ERROR", "1") == "1",
        "fallback_on_llm_error": os.getenv("FALLBACK_ON_LLM_ERROR", "1") == "1",
        "fallback_on_tts_error": os.getenv("FALLBACK_ON_TTS_ERROR", "1") == "1",

        # Transcript
        "enable_transcript": os.getenv("ENABLE_TRANSCRIPT", "1") == "1",
        "transcript_dir": os.getenv("TRANSCRIPT_DIR", "./logs/transcripts"),
        "transcript_timestamps": os.getenv("TRANSCRIPT_TIMESTAMPS", "1") == "1",
        "transcript_prefix": os.getenv("TRANSCRIPT_PREFIX", "conversation"),

        # Fillers
        "enable_fillers": os.getenv("ENABLE_FILLERS", "1") == "1",
        "filler_probability": float(os.getenv("FILLER_PROBABILITY", "0.4")),
        "filler_texts": [
            t.strip() for t in os.getenv(
                "FILLER_TEXTS",
                "Umm...,Hmm...,Ah...,Mmm...,Let me check...,Sure one moment...,Okay..."
            ).split(",") if t.strip()
        ],

        # Analytics
        "enable_analytics": os.getenv("ENABLE_ANALYTICS", "1") == "1",
        "analytics_file": os.getenv("ANALYTICS_FILE", "./logs/analytics/conversation_analytics.xlsx"),
        "analytics_auto_save": os.getenv("ANALYTICS_AUTO_SAVE", "1") == "1",
    }

    return config


def print_configuration(config: dict):
    """Print configuration summary."""
    table = Table(
        title="🤖 Voicebot V2 Enhanced - Configuration",
        show_header=True,
        header_style="bold magenta",
    )
    table.add_column("Module", style="cyan", width=20)
    table.add_column("Status", style="green", width=12)
    table.add_column("Details", style="white")

    # Audio
    table.add_row(
        "Audio I/O",
        "✓ Enabled",
        f"Sample Rate: {config['sample_rate']}Hz, VAD: {config['vad_aggr']}, Frame: {config['frame_ms']}ms",
    )

    # Barge-in
    status = "✓ Enabled" if config["enable_barge_in"] else "✗ Disabled"
    details = (
        f"Trigger: {config['barge_in_trigger_ms']}ms, Sensitivity: {config['barge_in_sensitivity']}"
        if config["enable_barge_in"]
        else "N/A"
    )
    table.add_row("Barge-in", status, details)

    # Denoiser
    status = "✓ Enabled" if config["enable_denoiser"] else "✗ Disabled"
    details = (
        f"Type: {config['denoiser_type']}, Strength: {config['denoiser_strength']}"
        if config["enable_denoiser"]
        else "N/A"
    )
    table.add_row("Audio Denoiser", status, details)

    # STT
    stt_p = config["stt_provider"].upper()
    status = "✓ Enabled" if config["enable_stt"] else "✗ Disabled"
    if config["stt_provider"] == "deepgram":
        ml = " (multilingual)" if config.get("deepgram_multilingual") else ""
        details = f"Provider: Deepgram, Model: {config['deepgram_model']}, Lang: {config['deepgram_language']}{ml}"
    else:
        details = f"Provider: Whisper, Model: {config['whisper_model']}, Device: {config['whisper_device']}"
    table.add_row(f"STT ({stt_p})", status, details)

    # LLM
    status = "✓ Enabled" if config["enable_llm"] else "✗ Disabled"
    details = (
        f"Model: {config['groq_model']}, Temp: {config['groq_temperature']}, MaxTokens: {config['groq_max_tokens']}"
        if config["enable_llm"]
        else "N/A"
    )
    table.add_row("LLM (Groq)", status, details)

    # TTS
    tts_p = config["tts_provider"].upper()
    status = "✓ Enabled" if config["enable_tts"] else "✗ Disabled"
    if config["tts_provider"] == "sarvam":
        details = f"Provider: Sarvam AI, Speaker: {config['sarvam_speaker']}, Lang: {config['sarvam_language']}"
    else:
        tts_mode = "Streaming" if config["elevenlabs_streaming"] else "Non-streaming"
        details = f"Provider: ElevenLabs, Model: {config['elevenlabs_model_id']}, Mode: {tts_mode}"
    table.add_row(f"TTS ({tts_p})", status, details)

    # Async
    status = "✓ Enabled" if config["enable_async"] else "✗ Disabled"
    table.add_row(
        "Async Mode",
        status,
        f"Timeout: {config['async_timeout']}s" if config["enable_async"] else "N/A",
    )

    # Fillers
    status = "✓ Enabled" if config["enable_fillers"] else "✗ Disabled"
    details = f"Probability: {int(config['filler_probability']*100)}%, Clips: {len(config['filler_texts'])}" if config["enable_fillers"] else "N/A"
    table.add_row("Fillers", status, details)

    # Transcript
    status = "✓ Enabled" if config["enable_transcript"] else "✗ Disabled"
    table.add_row(
        "Transcript",
        status,
        f"Dir: {config['transcript_dir']}" if config["enable_transcript"] else "N/A",
    )

    # Analytics
    status = "✓ Enabled" if config["enable_analytics"] else "✗ Disabled"
    table.add_row(
        "Analytics",
        status,
        f"File: {config['analytics_file']}" if config["enable_analytics"] else "N/A",
    )

    # Logging
    status = "✓ Enabled" if config["log_events_to_file"] else "✗ Disabled"
    table.add_row(
        "Event Logging",
        status,
        f"File: {config['events_file']}, Level: {config['log_level']}"
        if config["log_events_to_file"]
        else "N/A",
    )

    console.print(table)
    console.print()


def _build_stt(config: dict):
    """Instantiate the correct STT provider based on STT_PROVIDER env var."""
    if config["stt_provider"] == "deepgram":
        from src.providers.stt_deepgram import create_stt
        mode = config["deepgram_stt_mode"]
        console.print(f"[cyan]  STT → Deepgram (cloud) [{mode}][/cyan]")
        return create_stt(
            mode=mode,
            enabled=config["enable_stt"],
            api_key=config["deepgram_api_key"],
            model=config["deepgram_model"],
            language=config["deepgram_language"],
            multilingual=config["deepgram_multilingual"],
            punctuate=config["deepgram_punctuate"],
            smart_format=config["deepgram_smart_format"],
            timeout=config["deepgram_timeout"],
            enable_async=config["enable_async"],
            sample_rate=config["sample_rate"],
            endpointing_ms=config["deepgram_endpointing_ms"],
            utterance_end_ms=config["deepgram_utterance_end_ms"],
        )
    else:
        console.print("[cyan]  STT → Faster-Whisper (local)[/cyan]")
        return FasterWhisperSTT(
            enabled=config["enable_stt"],
            model_name=config["whisper_model"],
            device=config["whisper_device"],
            compute_type=config["whisper_compute_type"],
            language=config["whisper_language"],
            vad_filter=config["whisper_vad_filter"],
            beam_size=config["whisper_beam_size"],
            enable_async=config["enable_async"],
            timeout=config["async_timeout"],
        )


def _build_tts(config: dict):
    """Instantiate the correct TTS provider based on TTS_PROVIDER env var."""
    if config["tts_provider"] == "sarvam":
        from src.providers.tts_sarvam import SarvamTTS
        console.print("[cyan]  TTS → Sarvam AI (Indian voices)[/cyan]")
        return SarvamTTS(
            enabled=config["enable_tts"],
            api_key=config["sarvam_api_key"],
            model=config["sarvam_model"],
            speaker=config["sarvam_speaker"],
            language=config["sarvam_language"],
            pitch=config["sarvam_pitch"],
            pace=config["sarvam_pace"],
            loudness=config["sarvam_loudness"],
            temperature=config["sarvam_temperature"],
            timeout=config["sarvam_timeout"],
            enable_async=config["enable_async"],
        )
    else:
        console.print("[cyan]  TTS → ElevenLabs[/cyan]")
        return ElevenLabsTTS(
            enabled=config["enable_tts"],
            api_key=config["elevenlabs_api_key"],
            voice_id=config["elevenlabs_voice_id"],
            model_id=config["elevenlabs_model_id"],
            output_format=config["elevenlabs_output_format"],
            stability=config["elevenlabs_stability"],
            similarity_boost=config["elevenlabs_similarity_boost"],
            style=config["elevenlabs_style"],
            speaker_boost=config["elevenlabs_speaker_boost"],
            timeout=config["elevenlabs_timeout"],
            enable_streaming=config["elevenlabs_streaming"],
            enable_async=config["enable_async"],
        )


def initialize_components(config: dict):
    """Initialize all components from configuration."""

    # Denoiser
    denoiser = create_denoiser_from_env(
        enabled=config["enable_denoiser"],
        denoiser_type=config["denoiser_type"],
        strength=config["denoiser_strength"],
        stationary=config["denoiser_stationary"],
        sample_rate=config["sample_rate"],
    )

    # Audio I/O
    audio = AudioIO(
        sample_rate=config["sample_rate"],
        frame_ms=config["frame_ms"],
        vad_aggressiveness=config["vad_aggr"],
        end_silence_ms=config["end_silence_ms"],
        max_utterance_sec=config["max_utt_sec"],
        enable_barge_in=config["enable_barge_in"],
        barge_in_trigger_ms=config["barge_in_trigger_ms"],
        barge_in_sensitivity=config["barge_in_sensitivity"],
        denoiser=denoiser,
        enable_async=config["enable_async"],
        buffer_size=config["buffer_size"],
        log_audio_stats=config["log_audio_stats"],
    )

    # STT — provider selected from .env
    stt = _build_stt(config)

    # LLM
    llm = GroqLLM(
        enabled=config["enable_llm"],
        api_key=config["groq_api_key"],
        model=config["groq_model"],
        temperature=config["groq_temperature"],
        max_tokens=config["groq_max_tokens"],
        timeout=config["groq_timeout"],
        max_retries=config["groq_max_retries"],
        enable_async=config["enable_async"],
    )

    # TTS — provider selected from .env
    tts = _build_tts(config)

    # Stores
    customer_store = CustomerContextStore(config["customers_csv"])
    faq_store = FAQStore(config["faqs_json"])

    # Logger
    logger = EventLogger(
        to_file=config["log_events_to_file"],
        file_path=config["events_file"],
    )

    # Transcript
    transcript = create_transcript_from_env(
        enabled=config["enable_transcript"],
        output_dir=config["transcript_dir"],
        include_timestamps=config["transcript_timestamps"],
        session_prefix=config["transcript_prefix"],
    )

    # Analytics
    analytics = create_analytics_from_env(
        enabled=config["enable_analytics"],
        output_file=config["analytics_file"],
        auto_save=config["analytics_auto_save"],
    )

    if analytics and analytics.enabled:
        analytics.update_config(config)

    # Customer context
    customer_context = {}
    if config["lookup_val"]:
        customer_context = customer_store.lookup(config["lookup_key"], config["lookup_val"])

    # Filler manager — pre-synthesizes clips at startup
    filler_manager = None
    if config["enable_fillers"]:
        # Use v3 (Pooja) for fillers — v2 (Anushka) handles short sounds poorly.
        # v3 is only used for pre-cached filler synthesis at startup, not live TTS.
        from src.providers.tts_sarvam import SarvamTTS as _SarvamTTS
        filler_tts = _SarvamTTS(
            enabled=True,
            api_key=config["sarvam_api_key"],
            model="bulbul:v3",
            speaker="pooja",
            language=config.get("sarvam_language", "en-IN"),
            temperature=0.6,
        )
        filler_manager = FillerManager(
            tts=filler_tts,
            audio=audio,
            enabled=True,
            probability=config["filler_probability"],
            filler_texts=config["filler_texts"],
        )

    return {
        "audio": audio,
        "stt": stt,
        "llm": llm,
        "tts": tts,
        "faq_store": faq_store,
        "logger": logger,
        "transcript": transcript,
        "analytics": analytics,

        "knowledge_mode": config["knowledge_mode"],   # <-- ADD THIS
        
        "customer_context": customer_context,
        "system_prompt_path": config["system_prompt"],
        "greeting_prompt_path": config["greeting_prompt"],
        "llm_max_words": config["llm_max_words"],
        "llm_context_turns": config["llm_context_turns"],
        "llm_summarise_every": config["llm_summarise_every"],
        "silence_timeout_sec": config["silence_timeout_sec"],
        "silence_max_prompts": config["silence_max_prompts"],
        "llm_tts_streaming": config["llm_tts_streaming"],
        "llm_json_instructions_path": config["llm_json_instructions"],
        "fallback_on_stt_error": config["fallback_on_stt_error"],
        "fallback_on_llm_error": config["fallback_on_llm_error"],
        "fallback_on_tts_error": config["fallback_on_tts_error"],
        "filler_manager": filler_manager,
    }


def print_stats(components: dict):
    """Print performance statistics."""
    console.print("\n[bold cyan]📊 Session Statistics[/bold cyan]")

    audio_stats = components["audio"].get_stats()
    console.print(
        f"  Audio: {audio_stats['recordings']} recordings, "
        f"{audio_stats['barge_ins']} barge-ins, "
        f"{audio_stats['denoised']} denoised"
    )

    stt_stats = components["stt"].get_stats()
    if stt_stats.get("transcriptions", 0) > 0:
        console.print(
            f"  STT: {stt_stats['transcriptions']} transcriptions, "
            f"RTF: {stt_stats.get('real_time_factor', 0):.2f}x"
        )

    llm_stats = components["llm"].get_stats()
    if llm_stats.get("completions", 0) > 0:
        console.print(
            f"  LLM: {llm_stats['completions']} completions, "
            f"{llm_stats['total_tokens']} tokens, "
            f"{llm_stats['retries']} retries"
        )

    tts_stats = components["tts"].get_stats()
    if tts_stats.get("synthesized", 0) > 0:
        console.print(
            f"  TTS: {tts_stats['synthesized']} synthesized, "
            f"{tts_stats['total_chars']} chars"
        )

    if components.get("transcript") and components["transcript"].enabled:
        console.print(f"  Transcript: {components['transcript'].get_filepath()}")

    if components.get("analytics") and components["analytics"].enabled:
        console.print(f"  Analytics: {components['analytics'].get_summary()}")

    console.print()


def run():
    """Main entry point."""
    console.print("[bold green]🚀 Voicebot V2 Enhanced[/bold green]")
    console.print("Loading configuration from .env file...\n")

    config = load_config()
    print_configuration(config)

    # Validate critical settings
    if config["enable_llm"] and not config["groq_api_key"]:
        console.print("[bold red]Error: LLM enabled but GROQ_API_KEY not set in .env[/bold red]")
        sys.exit(1)

    if config["enable_tts"] and config["tts_provider"] == "elevenlabs" and not config["elevenlabs_api_key"]:
        console.print("[bold red]Error: TTS=elevenlabs but ELEVENLABS_API_KEY not set in .env[/bold red]")
        sys.exit(1)

    if config["enable_tts"] and config["tts_provider"] == "sarvam" and not config["sarvam_api_key"]:
        console.print("[bold red]Error: TTS=sarvam but SARVAM_API_KEY not set in .env[/bold red]")
        sys.exit(1)

    if config["enable_stt"] and config["stt_provider"] == "deepgram" and not config["deepgram_api_key"]:
        console.print("[bold red]Error: STT=deepgram but DEEPGRAM_API_KEY not set in .env[/bold red]")
        sys.exit(1)

    # Initialize components
    console.print("[cyan]Initializing components...[/cyan]")
    components = initialize_components(config)

    # Create orchestrator
    bot = OrchestratorV2(
        audio=components["audio"],
        stt=components["stt"],
        llm=components["llm"],
        tts=components["tts"],
        faq_store=components["faq_store"],
        system_prompt_path=components["system_prompt_path"],
        greeting_prompt_path=components.get("greeting_prompt_path", "./config/prompts/greeting.txt"),
        llm_max_words=components.get("llm_max_words", 50),
        llm_context_turns=components.get("llm_context_turns", 5),
        summarise_every=components.get("llm_summarise_every", 3),
        silence_timeout_sec=components.get("silence_timeout_sec", 8),
        silence_max_prompts=components.get("silence_max_prompts", 2),
        llm_tts_streaming=components.get("llm_tts_streaming", False),
        llm_json_instructions_path=components["llm_json_instructions_path"],
        customer_context=components["customer_context"],
        logger=components["logger"],
        transcript=components["transcript"],
        analytics=components["analytics"],
        fallback_on_stt_error=components["fallback_on_stt_error"],
        fallback_on_llm_error=components["fallback_on_llm_error"],
        fallback_on_tts_error=components["fallback_on_tts_error"],
        filler_manager=components.get("filler_manager"),
        knowledge_mode=components["knowledge_mode"],   # ←  newly added(for switch)
    )

    console.print("[bold green]✓ Ready![/bold green]")
    console.print(f"Customer context: {list(components['customer_context'].keys())}")
    console.print("\n[yellow]Press Ctrl+C to stop and view statistics[/yellow]\n")

    try:
        bot.run_loop()
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping...[/yellow]")
        print_stats(components)
        console.print("[green]Goodbye![/green]")


if __name__ == "__main__":
    run()