"""
OrchestratorV2 — KB-only, no script_blocks.

Per-turn flow:
  1. Record utterance
  2. STT → transcript + detected language
  3. Update TTS language
  4. FAQRouter → top KB matches injected into LLM prompt
  5. LLM → intent + natural language response in user's language
  6. TTS → speak response
"""
import time
import queue
import threading
from typing import Any, Dict, Iterator, List, Optional

from rich.console import Console
from rich.rule import Rule

from src.core.state import ConversationState
from src.core.utils import read_text, safe_json_loads
from src.context.template import render_template
from src.faq.router import FAQRouter
from src.core.handover import transfer
from src.core.summariser import ConversationSummariser
from src.faq.store import FAQStore
from src.core.logger import EventLogger
from src.analytics.transcript import ConversationTranscript
from src.analytics.analytics import ConversationAnalytics
from src.core.filler import FillerManager
from src.rag.doc_search import search
console = Console()

LANG_DISPLAY = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "mr-IN": "Marathi",
    "bn-IN": "Bengali",
    "gu-IN": "Gujarati",
    
}

# Fallback responses when LLM returns nothing usable
FALLBACK_RESPONSE = "I'm sorry, I didn't quite get that. Could you say it again?"
FALLBACK_RESPONSE_HI = "Maafi karein, mujhe samajh nahi aaya. Kya aap dobara bol sakte hain?"


class OrchestratorV2:
    def __init__(
        self,
        audio,
        stt,
        llm,
        tts,
        faq_store: FAQStore,
        system_prompt_path: str,
        llm_json_instructions_path: str,
        customer_context: Dict[str, Any],
        logger: EventLogger,
        greeting_prompt_path: str = "./config/prompts/greeting.txt",
        llm_max_words: int = 50,
        llm_context_turns: int = 5,
        summarise_every: int = 3,
        silence_timeout_sec: int = 8,
        silence_max_prompts: int = 2,
        llm_tts_streaming: bool = False,
        event_sink=None,   # optional callable(type, data) for browser events
        transcript: Optional[ConversationTranscript] = None,
        analytics: Optional[ConversationAnalytics] = None,
        fallback_on_stt_error: bool = True,
        fallback_on_llm_error: bool = True,
        fallback_on_tts_error: bool = True,
        filler_manager: Optional[FillerManager] = None,
        knowledge_mode: str = "faq",
    ):
        self.audio = audio
        self.stt   = stt
        self.llm   = llm
        self.tts   = tts

        self.router = FAQRouter(faq_store.all())
        self.logger = logger
        self.state  = ConversationState()

        self.transcript = transcript
        self.analytics  = analytics

        self.system_prompt         = render_template(read_text(system_prompt_path), customer_context or {})
        self.llm_json_instructions  = read_text(llm_json_instructions_path)
        # Build greeting context — customer_name_greeting is " Shivam" if known, "" if unknown
        _ctx = customer_context or {}
        _name = (_ctx.get("customer_name") or "").strip()
        _greeting_ctx = {**_ctx, "customer_name_greeting": f" {_name}" if _name else ""}
        _raw_greeting = render_template(read_text(greeting_prompt_path), _greeting_ctx)
        # Strip any remaining unresolved {placeholders} so they never reach TTS
        import re as _re
        self.greeting = _re.sub(r'\{[^}]+\}', '', _raw_greeting).strip()
        self.llm_max_words          = llm_max_words
        self.llm_context_turns      = llm_context_turns
        self.summariser             = ConversationSummariser(llm, summarise_every=summarise_every)
        # Detect mode — streaming STT has a different run loop
        from src.providers.stt_deepgram import DeepgramStreamingSTT
        self._streaming_mode = isinstance(stt, DeepgramStreamingSTT)
        self.silence_timeout_sec    = silence_timeout_sec
        self.silence_max_prompts    = silence_max_prompts
        self.llm_tts_streaming      = llm_tts_streaming
        self._event_sink             = event_sink
        self.customer_context     = customer_context or {}
        self.knowledge_mode = knowledge_mode

        self.fallback_on_stt_error = fallback_on_stt_error
        self.fallback_on_llm_error = fallback_on_llm_error
        self.fallback_on_tts_error = fallback_on_tts_error

        self.filler = filler_manager

        self._current_language = "en-IN"

        self._latency_totals = {
            "stt": 0.0, "llm": 0.0,
            "tts_first_chunk": 0.0, "tts_playback": 0.0, "total": 0.0,
        }
        self._turn_count = 0

    def _emit(self, event_type: str, data: dict):
        """Send event to browser frontend if event_sink is set."""
        if self._event_sink:
            try:
                self._event_sink(event_type, data)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # Language
    # ─────────────────────────────────────────────────────────────────────────

    def _update_language(self, detected: str):
        if detected == self._current_language:
            return
        prev = LANG_DISPLAY.get(self._current_language, self._current_language)
        curr = LANG_DISPLAY.get(detected, detected)
        console.print(f"  [dim]🌐 Language: {prev} → {curr}[/dim]")
        self._current_language = detected
        if hasattr(self.tts, "set_language"):
            self.tts.set_language(detected)

    def _emit(self, event_type: str, data: dict):
        """Send event to browser frontend if event_sink is set."""
        if self._event_sink:
            try:
                self._event_sink(event_type, data)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # Language
    # ─────────────────────────────────────────────────────────────────────────

    # def _update_language(self, detected: str):
       # """Switch TTS language when user changes language."""
       #if detected == self._current_language:
           # return
       #self._current_language = detected
        #if hasattr(self.tts, "set_language"):
            #self.tts.set_language(detected)

    # ─────────────────────────────────────────────────────────────────────────
    # LLM
    # ─────────────────────────────────────────────────────────────────────────

    def _build_messages(self, user_text: str) -> List[Dict[str, str]]:
        lang_name = LANG_DISPLAY.get(self._current_language, self._current_language)
        context_compact = {k: v for k, v in self.customer_context.items() if v}

        # Build context-enriched query for KB matching:
        # Take last 3 user turns (current turn is already in history).
        # This means short follow-ups like "tell me how to do it" are matched
        # with full context from prior turns e.g. "can i cancel my sip".
        recent_user_turns = [
            h["text"] for h in self.state.history
            if h["role"] == "user"
        ][-self.llm_context_turns:]  # last N user turns for KB matching
        context_query = " ".join(recent_user_turns).strip()

       

        # Inject current word limit into instructions
        instructions = self.llm_json_instructions.replace(
            "{LLM_MAX_WORDS}", str(self.llm_max_words)
        )

        print("KNOWLEDGE MODE:", self.knowledge_mode)

        kb_block = ""
        doc_block = ""

        if self.knowledge_mode == "faq":

          kb_hits = self.router.get_kb_context(context_query, k=2)

          if kb_hits:
            kb_lines = "\n".join(
              f"  [{h['faq_id']}] Q: {h['question']}\n  A: {h['answer']}"
              for h in kb_hits
        )

          kb_block = (
            f"\n\nKB_CONTEXT (paraphrase naturally in {lang_name} if relevant):\n"
            + kb_lines
        )

        elif self.knowledge_mode == "rag":

            doc_result = search(context_query)
            print("DOCUMENT RESULT:", doc_result)

            if doc_result:
              doc_block = (
                  "\n\nDOCUMENT_CONTEXT:\n"
                  + doc_result["text"]
                  + "\n\nIMPORTANT:"
                  + "\nAnswer ONLY using DOCUMENT_CONTEXT."
                  + "\nIf the answer is not present in DOCUMENT_CONTEXT, say you do not know."
        )

        # Build recent conversation history for LLM context (last 3 turns)
        recent_history = self.state.history[-(self.llm_context_turns * 2):]  # each turn = 2 entries (user+bot)
        history_text = ""
        if len(recent_history) > 2:  # only include if there's prior context
            lines = []
            for h in recent_history[:-1]:  # exclude current turn (sent as user message)
                prefix = "Customer" if h["role"] == "user" else "Bot"
                lines.append(f"{prefix}: {h['text']}")
            history_text = "\n\nRECENT_CONVERSATION:\n" + "\n".join(lines)

        system = (
            self.system_prompt
            + self.summariser.get_context_block()
            + "\n\nINSTRUCTIONS:\n"
            + instructions
            + f"\n\nCUSTOMER_CONTEXT: {context_compact}"
            + f"\nDETECTED_LANGUAGE: {self._current_language} ({lang_name})"
            + f"\nREPLY_IN: {lang_name} — always reply in this language."
            + f"\nCustomer spoke {lang_name}. Always reply in {lang_name}."
            + history_text
            + kb_block
            + doc_block
        )
        
        return [
            {"role": "system", "content": system},
            {"role": "user",   "content": user_text},
        ]

    def _call_llm(self, user_text: str) -> Dict[str, Any]:
        original_language = self._current_language
        try:
            english_text = user_text

            if original_language != "en-IN":
               english_text = self.llm.translate_to_english(user_text)

            raw = self.llm.complete(
               self._build_messages(english_text)
)
           
            self.logger.log("llm_raw", {"raw": raw})
            plan = safe_json_loads(raw)
            
        except Exception as e:
            print("\nLLM ERROR:")
            print(e)
            print()
            self.logger.log("llm_error", {"error": str(e)})
            if not self.fallback_on_llm_error:
                raise
            plan = {"intent": "fallback", "say": ""}

        say = (plan.get("say") or "").strip()
        if not say:
            lang = self._current_language
            plan["say"] = FALLBACK_RESPONSE_HI if lang == "hi-IN" else FALLBACK_RESPONSE

        return plan

    # ─────────────────────────────────────────────────────────────────────────
    # TTS prefetch
    # ─────────────────────────────────────────────────────────────────────────

    def _prefetch_tts(self, text: str, chunk_queue: queue.Queue,
                      latencies: dict, t0: float, error_box: list):
        first = True
        try:
            for chunk in self.tts.stream(text):
                if first:
                    latencies["tts_first_chunk"] = time.time() - t0
                    first = False
                chunk_queue.put(chunk)
        except Exception as e:
            error_box.append(e)
        finally:
            chunk_queue.put(None)

    # ─────────────────────────────────────────────────────────────────────────
    # Terminal display
    # ─────────────────────────────────────────────────────────────────────────

    def _print_turn_header(self, turn: int):
        console.print()  # ensure we start on a fresh line after partials
        console.print(Rule(f"[bold white] Turn {turn} [/bold white]", style="dim"))

    def _print_latency(self, latencies: Dict[str, float]):
        def _col(ms):
            if ms < 400:   return f"[green]{ms:.0f}ms[/green]"
            elif ms < 800: return f"[yellow]{ms:.0f}ms[/yellow]"
            else:          return f"[red]{ms:.0f}ms[/red]"

        stt_ms  = latencies.get("stt", 0)             * 1000
        llm_ms  = latencies.get("llm", 0)             * 1000
        # In streaming STT mode, stt=0 — show actual utterance lag if available
        stt_ms  = latencies.get("stt_actual", stt_ms)
        # In streaming TTS mode, tts_first_chunk=0 — use tts_playback instead
        tts_ms  = latencies.get("tts_first_chunk", 0) * 1000
        play_ms = latencies.get("tts_playback", 0)    * 1000
        if tts_ms == 0 and play_ms > 0:
            tts_ms = play_ms   # streaming mode: playback IS the TTS metric
        tot_ms  = latencies.get("total", 0)            * 1000

        mode_tag = "[dim](stream)[/dim]" if self._streaming_mode else ""
        console.print(
            f"  [dim]⏱  STT[/dim] {_col(stt_ms)}  "
            f"[dim]LLM[/dim] {_col(llm_ms)}  "
            f"[dim]TTS+Play[/dim] {_col(tts_ms)}  "
            f"[dim]│ Total[/dim] [bold]{tot_ms:.0f}ms[/bold] {mode_tag}"
        )

    def _print_avg_stats(self):
        if self._turn_count == 0:
            return
        n = self._turn_count
        console.print(
            f"\n[bold cyan]📊 Avg latency over {n} turn(s):[/bold cyan]  "
            f"STT {self._latency_totals['stt']/n*1000:.0f}ms  "
            f"LLM {self._latency_totals['llm']/n*1000:.0f}ms  "
            f"TTS+Play {self._latency_totals['tts_playback']/n*1000:.0f}ms  "
            f"Total {self._latency_totals['total']/n*1000:.0f}ms"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Queue helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _wait_for_first_chunk(self, q: queue.Queue, timeout: float = 3.0):
        try:
            q._peeked = q.get(timeout=timeout)  # type: ignore[attr-defined]
        except queue.Empty:
            pass

    def _drain_queue(self, q: queue.Queue) -> Iterator[bytes]:
        peeked = getattr(q, "_peeked", None)
        if peeked is not None:
            q._peeked = None  # type: ignore[attr-defined]
            yield peeked
        while True:
            try:
                chunk = q.get(timeout=5.0)
                if chunk is None:
                    break
                yield chunk
            except queue.Empty:
                break

    # ─────────────────────────────────────────────────────────────────────────
    # Main loop
    # ─────────────────────────────────────────────────────────────────────────

    # ─────────────────────────────────────────────────────────────────────────
    # Streaming run loop
    # ─────────────────────────────────────────────────────────────────────────

    def _run_streaming(self) -> None:
        """
        Streaming STT run loop.
        Audio streams continuously to Deepgram. When speech_final fires,
        the on_utterance callback queues the transcript for processing.
        """
        import queue as _queue
        utterance_queue: _queue.Queue = _queue.Queue()
        stop_event      = threading.Event()
        speech_active   = threading.Event()  # set while partials are arriving
        barge_in_event  = threading.Event()  # set when customer speaks during playback

        def on_utterance(transcript: str, language: str) -> None:
            speech_active.clear()
            barge_in_event.clear()
            utterance_queue.put((transcript, language))
         

        def on_partial(text: str) -> None:
            speech_active.set()
            _bot_spk = getattr(self, "_bot_speaking_event", None)
            if not barge_in_event.is_set():
                # First partial in this burst — log context
                if _bot_spk and _bot_spk.is_set():
                    console.print(f"\n  [yellow]⚡ Barge-in triggered during bot speech: '{text}'[/yellow]")
                else:
                    console.print(f"\n  [dim]Partial during silence: '{text}'[/dim]")

                   
                    barge_in_event.set()
            console.print(f"\r  [dim]…{text}[/dim]          ", end="")
            self._emit("partial", {"text": text})

        # Wire callback and start WebSocket
        self.stt.on_utterance    = on_utterance
        self.stt.on_partial      = on_partial
        bot_speaking             = threading.Event()  # tracks when bot TTS is playing
        mic_muted                = threading.Event()  # set to pause mic → Deepgram during TTS
        self._barge_in_event     = barge_in_event   # used by _process_turn
        self._bot_speaking_event = bot_speaking      # used by _process_turn
        self._mic_muted          = mic_muted         # used by _process_turn
        self.stt.start()
        console.print("[dim]  STT WebSocket connected[/dim]")

        # Start mic streaming in background thread
        mic_thread = threading.Thread(
            target=self.audio.stream_to_stt,
            args=(self.stt, stop_event, mic_muted),
            daemon=True,
        )
        mic_thread.start()

        try:
            while True:
                try:
                    # Wait for next utterance (with silence timeout check)
                    try:
                        user_text, detected_lang = utterance_queue.get(
                            timeout=self.silence_timeout_sec
                        )
                        self._silence_strikes = 0
                        speech_active.clear()
                    except _queue.Empty:
                        # Only count as silence if no partials are arriving
                        if speech_active.is_set():
                            speech_active.clear()
                            continue   # customer was speaking — reset and wait again
                        # Genuine silence timeout
                        self._silence_strikes = getattr(self, "_silence_strikes", 0) + 1
                        if self._silence_strikes >= self.silence_max_prompts:
                            _farewell = (
                                "कोई जवाब न मिलने के कारण मैं call समाप्त कर रही हूं। "
                                "किसी भी सहायता के लिए फिर से call करें। धन्यवाद!"
                                if self._current_language == "hi-IN" else
                                "Due to no response I'm ending the call. "
                                "Feel free to reach out again. Thank you!"
                            )
                            console.print(f"  [bold green]Bot :[/bold green] {_farewell}  [dim](silence — ending call)[/dim]")
                            self.audio.play_tts_stream(
                                stream_iter=self.tts.stream(_farewell),
                                sample_rate=self.audio.sample_rate,
                            )
                            break
                        else:
                            _prompt = ("क्या आप अभी भी वहाँ हैं?"
                                       if self._current_language == "hi-IN"
                                       else "Are you still there?")
                            console.print(f"  [bold green]Bot :[/bold green] {_prompt}  [dim](silence prompt {self._silence_strikes}/{self.silence_max_prompts})[/dim]")
                            self.audio.play_tts_stream(
                                stream_iter=self.tts.stream(_prompt),
                                sample_rate=self.audio.sample_rate,
                            )
                            continue

                    self._process_turn(user_text, detected_lang,
                                         utterance_queue=utterance_queue)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    self.logger.log("unexpected_error", {"error": str(e)})
                    console.print(f"[red][Error] {e}[/red]")

        finally:
            stop_event.set()
            self.stt.stop()
            self._finalize_session()

    def _process_turn(self, user_text: str, detected_lang: str,
                       utterance_queue=None) -> None:
        """Process a single turn — shared by both batch and streaming loops."""
        turn_start = time.time()
        latencies: Dict[str, float] = {}

        self._update_language(detected_lang)
        
        console.print(f"[red]Detected Language:[/red] {detected_lang}")
        console.print(f"[red]Current Language:[/red] {self._current_language}")
        console.print(f"[red]Original User Text:[/red] {user_text}")

        self.state.history.append({"role": "user", "text": user_text})
        self.state.turn += 1
        lang_tag = LANG_DISPLAY.get(self._current_language, self._current_language)
        self._print_turn_header(self.state.turn)
        console.print(f"  [bold cyan]You :[/bold cyan] {user_text}  [dim]({lang_tag})[/dim]")
        self._emit("user_text", {"text": user_text, "language": self._current_language})

        self.logger.log("user_text", {"turn": self.state.turn, "text": user_text,
                                      "language": self._current_language})
        if self.transcript:
            self.transcript.log_user_message(user_text)
        if self.analytics:
            self.analytics.increment_turn()
            self.analytics.log_user_message(user_text)

        # Filler + LLM
        filler_played = False
        if self.filler:
            filler_played = self.filler.play_filler_async()
            if filler_played:
                console.print("  [dim]🎵 filler…[/dim]")
                self._emit("filler", {})

        t0 = time.time()

        plan = self._call_llm(user_text)

        latencies["llm"] = time.time() - t0
        latencies["llm"] = time.time() - t0
        self.logger.log("plan", {"turn": self.state.turn, "plan": plan})

        self.state.last_intent = plan.get("intent")
        self.state.last_faq_id = plan.get("faq_id")
        final_text = plan["say"]

        # Stop filler
        if filler_played and self.filler:
            self.filler.stop()

        # Handoff — skip TTS entirely, _handle_handoff speaks everything
        if plan.get("intent") == "handoff":
            intent_label = plan.get("intent", "?")
            console.print(f"  [bold green]Bot :[/bold green] {final_text}  [dim]({intent_label})[/dim]")
            self.state.history.append({"role": "bot", "text": final_text})
            self.summariser.maybe_summarise(self.state.history)
            if self.transcript:
                self.transcript.log_bot_message(final_text)
            self._handle_handoff(user_text, utterance_queue=utterance_queue)
            raise KeyboardInterrupt

        intent_label = plan.get("intent", "?")
        faq_label    = f" [{plan.get('faq_id')}]" if plan.get("faq_id") else ""
        console.print(f"  [bold green]Bot :[/bold green] {final_text}  "
                      f"[dim]({intent_label}{faq_label})[/dim]")
        self._emit("bot_text", {"text": final_text, "intent": intent_label,
                                "faq_id": plan.get("faq_id")})

        # Barge-in event (streaming mode only — None in batch mode)
        _barge_evt     = getattr(self, "_barge_in_event", None)
        _bot_speaking  = getattr(self, "_bot_speaking_event", None)
        _mic_muted     = getattr(self, "_mic_muted", None)
        if _barge_evt:
            _barge_evt.clear()
        if _bot_speaking:
            _bot_speaking.set()
        if _mic_muted:
            _mic_muted.set()   # mute during synthesis only

        try:
            t_play = time.time()
            if self.llm_tts_streaming:
                # Streaming: fire TTS per sentence, play in parallel
                import re as _re
                _SPLIT = _re.compile(r'(?<=[.!?।])\s+')
                def _sentence_iter(text):
                    parts = _SPLIT.split(text.strip())
                    for i, p in enumerate(parts):
                        yield p + (' ' if i < len(parts) - 1 else '')
                self.tts.stream_synthesize(
                    token_iter=_sentence_iter(final_text),
                    audio_io=self.audio,
                    barge_in_event=_barge_evt,
                    mic_muted=_mic_muted,
                )
            else:
                # Batch: prefetch full TTS then play
                chunk_queue: queue.Queue = queue.Queue(maxsize=32)
                tts_error_box: list = []
                tts_t0 = time.time()
                tts_thread = threading.Thread(
                    target=self._prefetch_tts,
                    args=(final_text, chunk_queue, latencies, tts_t0, tts_error_box),
                    daemon=True,
                )
                tts_thread.start()
                if not filler_played:
                    self._wait_for_first_chunk(chunk_queue, timeout=3.0)
                self.audio.play_tts_stream(
                    stream_iter=self._drain_queue(chunk_queue),
                    sample_rate=self.audio.sample_rate,
                    external_stop_event=_barge_evt,
                )
            latencies["tts_playback"] = time.time() - t_play

        except Exception as e:
            console.print(f"[red][TTS Error] {e}[/red]")
        finally:
            if _bot_speaking:
                _bot_speaking.clear()
            if _mic_muted:
                _mic_muted.clear()  # unmute mic — customer can speak again

        self.state.history.append({"role": "bot", "text": final_text})
        self.summariser.maybe_summarise(self.state.history)

        if self.transcript:
            self.transcript.log_bot_message(final_text)
        if self.analytics:
            self.analytics.log_bot_message(final_text)



        latencies["total"] = time.time() - turn_start
        self._print_latency(latencies)
        self._emit("latency", {"llm": latencies.get("llm"), "tts": latencies.get("tts_playback"), "total": latencies.get("total")})
        self._turn_count += 1
        for k in ("stt", "llm", "tts_first_chunk", "tts_playback", "total"):
            self._latency_totals[k] += latencies.get(k, 0.0)
        console.print()

    # ─────────────────────────────────────────────────────────────────────────
    # Batch run loop
    # ─────────────────────────────────────────────────────────────────────────

    def run_loop(self):
        # Play greeting immediately on call start
        console.print(f"  [bold green]Bot :[/bold green] {self.greeting}  [dim](greeting)[/dim]")
        self._emit("greeting", {"text": self.greeting})
        self.state.history.append({"role": "bot", "text": self.greeting})
        if self.transcript:
            self.transcript.log_bot_message(self.greeting)
        self.audio.play_tts_stream(
            stream_iter=self.tts.stream(self.greeting),
            sample_rate=self.audio.sample_rate,
        )
        console.print("\n[dim]Listening…[/dim]\n")

        if self._streaming_mode:
            self._run_streaming()
            return

        while True:
            try:
                turn_start = time.time()
                latencies: Dict[str, float] = {}

                # 1. Record
                pcm16, sr = self.audio.record_utterance()
                if not pcm16:
                    # No speech detected — check silence timeout
                    _elapsed = time.time() - turn_start
                    if _elapsed >= self.silence_timeout_sec:
                        self._silence_strikes = getattr(self, "_silence_strikes", 0) + 1
                        if self._silence_strikes >= self.silence_max_prompts:
                            # Max strikes — farewell and end call
                            _farewell = (
                                "कोई जवाब न मिलने के कारण मैं call समाप्त कर रही हूं। "
                                "किसी भी सहायता के लिए फिर से call करें। धन्यवाद, आपका दिन शुभ हो।"
                                if self._current_language == "hi-IN" else
                                "Due to no response I'm ending the call. "
                                "Feel free to reach out again if you need help. Thank you and have a great day!"
                            )
                            console.print(f"  [bold green]Bot :[/bold green] {_farewell}  [dim](silence — ending call)[/dim]")
                            self.audio.play_tts_stream(
                                stream_iter=self.tts.stream(_farewell),
                                sample_rate=self.audio.sample_rate,
                            )
                            self._finalize_session()
                            return
                        else:
                            # Prompt customer
                            _prompt = (
                                "क्या आप अभी भी वहाँ हैं?" if self._current_language == "hi-IN"
                                else "Are you still there?"
                            )
                            console.print(f"  [bold green]Bot :[/bold green] {_prompt}  [dim](silence prompt {self._silence_strikes}/{self.silence_max_prompts})[/dim]")
                            self.audio.play_tts_stream(
                                stream_iter=self.tts.stream(_prompt),
                                sample_rate=self.audio.sample_rate,
                            )
                    turn_start = time.time()
                    continue

                # Speech detected — reset silence counter
                self._silence_strikes = 0

                # 2. STT
                t0 = time.time()
                try:
                    if hasattr(self.stt, "transcribe_with_language"):
                        user_text, detected_lang = self.stt.transcribe_with_language(pcm16, sr)
                        user_text = user_text.strip()
                    else:
                        user_text     = self.stt.transcribe_pcm16(pcm16, sr).strip()
                        detected_lang = self._current_language
                except Exception as e:
                    self.logger.log("stt_error", {"error": str(e)})
                    if not self.fallback_on_stt_error:
                        raise
                    console.print(f"[red][STT Error] {e}[/red]")
                    user_text, detected_lang = "", self._current_language
                latencies["stt"] = time.time() - t0

                if not user_text:
                    continue

                # Update language — switches TTS voice before LLM runs
                self._update_language(detected_lang)

                # Append to conversation history for context-aware KB matching
                self.state.history.append({"role": "user", "text": user_text})

                self.state.turn += 1
                lang_tag = LANG_DISPLAY.get(self._current_language, self._current_language)
                self._print_turn_header(self.state.turn)
                console.print(f"  [bold cyan]You :[/bold cyan] {user_text}  [dim]({lang_tag})[/dim]")
                self._emit("user_text", {"text": user_text, "language": self._current_language})

                self.logger.log("user_text", {
                    "turn": self.state.turn, "text": user_text,
                    "language": self._current_language,
                })
                if self.transcript:
                    self.transcript.log_user_message(user_text)
                if self.analytics:
                    self.analytics.increment_turn()
                    self.analytics.log_user_message(user_text)

                # 4. Filler + LLM concurrently
                filler_played = False
                if self.filler:
                    filler_played = self.filler.play_filler_async()
                    if filler_played:
                        console.print("  [dim]🎵 filler…[/dim]")
                self._emit("filler", {})

                t0   = time.time()
                plan = self._call_llm(user_text)
                latencies["llm"] = time.time() - t0
                self.logger.log("plan", {"turn": self.state.turn, "plan": plan})

                # Track last intent/faq for context
                self.state.last_intent = plan.get("intent")
                self.state.last_faq_id = plan.get("faq_id")

                final_text = plan["say"]

                # 5. Start TTS prefetch immediately
                chunk_queue: queue.Queue = queue.Queue(maxsize=32)
                tts_error_box: list = []
                tts_t0 = time.time()
                tts_thread = threading.Thread(
                    target=self._prefetch_tts,
                    args=(final_text, chunk_queue, latencies, tts_t0, tts_error_box),
                    daemon=True,
                )
                tts_thread.start()

                # 6. Stop filler once first TTS chunk is buffered
                if filler_played and self.filler:
                    self.filler.stop()
                    self._wait_for_first_chunk(chunk_queue, timeout=3.0)

                intent_label = plan.get("intent", "?")
                faq_label    = f" [{plan.get('faq_id')}]" if plan.get("faq_id") else ""
                console.print(
                    f"  [bold green]Bot :[/bold green] {final_text}  "
                    f"[dim]({intent_label}{faq_label})[/dim]"
                )

                self.state.history.append({"role": "bot", "text": final_text})

                # Trigger rolling summary in background if enough turns accumulated
                self.summariser.maybe_summarise(self.state.history)

                if self.transcript:
                    self.transcript.log_bot_message(final_text)
                if self.analytics:
                    self.analytics.log_bot_message(final_text)

                # 7. Play
                try:
                    t_play = time.time()
                    # Pass barge-in event in streaming mode so on_partial
                    # can stop playback immediately when customer speaks
                    _barge_evt = getattr(self, "_barge_in_event", None)
                    if _barge_evt:
                        _barge_evt.clear()  # reset before playback starts
                    self.audio.play_tts_stream(
                        stream_iter=self._drain_queue(chunk_queue),
                        sample_rate=self.audio.sample_rate,
                        external_stop_event=_barge_evt,
                    )
                    latencies["tts_playback"] = time.time() - t_play

                    # 8. Handover — transfer call after bot finishes speaking
                    if plan.get("intent") == "handoff":
                        transfer(
                            customer_context=self.customer_context,
                            reason=user_text,
                        )
                        break  # end conversation loop
                    if tts_error_box:
                        raise tts_error_box[0]
                except Exception as e:
                    self.logger.log("tts_error", {"error": str(e)})
                    if not self.fallback_on_tts_error:
                        raise
                    console.print(f"[red][TTS Error] {e}[/red]")

                tts_thread.join(timeout=5.0)

                # 8. Latency
                latencies["total"] = time.time() - turn_start
                self._print_latency(latencies)
                self._turn_count += 1
                for k in ("stt", "llm", "tts_first_chunk", "tts_playback", "total"):
                    self._latency_totals[k] += latencies.get(k, 0.0)

                console.print()

            except KeyboardInterrupt:
                self._finalize_session()
                raise
            except Exception as e:
                self.logger.log("unexpected_error", {"error": str(e), "type": type(e).__name__})
                console.print(f"[red][Unexpected Error] {e}[/red]")

    # ─────────────────────────────────────────────────────────────────────────
    # Finalise
    # ─────────────────────────────────────────────────────────────────────────

    def _handle_handoff(self, reason: str, utterance_queue=None) -> None:
        """
        Speak confirmation question, listen for yes/no, then transfer or decline.
        utterance_queue: pass the live queue in streaming mode so we read from
        the WebSocket stream rather than fighting over the mic.
        """
        lang = self._current_language

        _confirm_q = (
            "यह जानकारी मेरे पास नहीं है, लेकिन एक senior representative आपकी मदद कर "
            "सकते हैं। क्या मैं आपको transfer करूं?"
            if lang == "hi-IN" else
            "I don't have that information right now, but a senior representative might "
            "be able to help. Would you like me to transfer you to them?"
        )
        console.print("  [dim]Speaking handoff confirmation question...[/dim]")
        self.audio.play_tts_stream(
            stream_iter=self.tts.stream(_confirm_q),
            sample_rate=self.audio.sample_rate,
        )
        console.print("  [dim]Waiting for handoff confirmation...[/dim]")

        try:
            if self._streaming_mode and utterance_queue is not None:
                import queue as _q
                # Flush any stale utterances queued before the confirmation question
                while not utterance_queue.empty():
                    try:
                        utterance_queue.get_nowait()
                    except _q.Empty:
                        break
                # Unmute mic so customer can answer
                _mc = getattr(self, "_mic_muted", None)
                if _mc:
                    _mc.clear()
                try:
                    confirm_text, _ = utterance_queue.get(timeout=10)
                except _q.Empty:
                    confirm_text = ""
            else:
                # Batch: record directly from mic
                pcm16, sr = self.audio.record_utterance()
                confirm_text, _ = (
                    self.stt.transcribe_with_language(pcm16, sr) if pcm16 else ("", "")
                )

            console.print(f"  [bold cyan]You :[/bold cyan] {confirm_text}  [dim](handoff confirmation)[/dim]")

            confirm_lower = confirm_text.lower().strip()
            console.print(f"  [dim]Confirmation heard: '{confirm_lower}'[/dim]")

            yes_words = {
                "yes", "yeah", "sure", "okay", "ok", "please",
                "transfer", "connect", "go ahead", "do it",
                "haan", "han", "ha", "haa", "ji", "ji haan", "ji han",
                "bilkul", "zaroor", "theek", "theek hai", "kar do",
                "haan ji", "yes please", "acha", "achha",
                "हां", "हाँ", "हा", "जी", "जी हाँ", "जी हां",
                "ज़रूर", "बिल्कुल", "ठीक है", "करो", "कर दो",
            }
            confirmed = any(w in confirm_lower for w in yes_words)

            if confirmed:
                transfer(customer_context=self.customer_context, reason=reason)
            else:
                decline_msg = (
                    "ठीक है, कोई बात नहीं। किसी और सहायता के लिए हमें call करें। धन्यवाद!"
                    if lang == "hi-IN" else
                    "No problem at all! Feel free to reach out if you need help. "
                    "Thank you and have a great day!"
                )
                console.print(f"  [bold green]Bot :[/bold green] {decline_msg}  [dim](handoff declined)[/dim]")
                self.audio.play_tts_stream(
                    stream_iter=self.tts.stream(decline_msg),
                    sample_rate=self.audio.sample_rate,
                )

        except Exception as e:
            print(f"[Handoff] Confirmation error: {e}")
            transfer(customer_context=self.customer_context, reason=reason)


    def _finalize_session(self):
        if self.analytics:
            self.analytics.update_from_component_stats("audio", self.audio.get_stats())
            self.analytics.update_from_component_stats("stt",   self.stt.get_stats())
            self.analytics.update_from_component_stats("llm",   self.llm.get_stats())
            self.analytics.update_from_component_stats("tts",   self.tts.get_stats())
        if self.transcript:
            self.transcript.finalize()
            console.print(f"\n[cyan]Transcript saved to:[/cyan] {self.transcript.get_filepath()}")
        if self.analytics:
            self.analytics.finalize()
            console.print(f"[cyan]Analytics:[/cyan] {self.analytics.get_summary()}")
        self._print_avg_stats()

        # Save call summary
        if self.state.history:
            filepath = self.summariser.save_call_summary(
                self.state.history, self.customer_context
            )
            console.print(f"[cyan]Call summary saved to:[/cyan] {filepath}")