"""
Conversation Summariser

Rolling summary strategy:
- Every SUMMARISE_EVERY turns, compress oldest unsummarised turns into
  a running summary via a cheap LLM call (tiny prompt, no JSON overhead).
- LLM context = SUMMARY block + last N full turns.
- Token saving: ~3 full turns (300 tokens) → 2-line summary (~40 tokens).

Call summary:
- On session end, generate a full call summary and save to logs/call_summaries/.
"""
import os
import threading
import requests
from datetime import datetime
from typing import List, Dict, Optional


# How many turns to keep as full text before compressing older ones
SUMMARISE_EVERY   = 3   # compress a batch of this many turns into summary
SUMMARY_MAX_LINES = 10  # cap rolling summary length (oldest lines drop off)

_ROLLING_PROMPT = """\
You are summarising a customer service call for internal notes. 
Be brief — one short line per exchange, like:
"Customer asked about SIP cancel meaning — bot explained it stops SIP permanently (KB)"
"Customer asked how to cancel — bot gave steps via MF Reports (KB)"
"Customer asked about NAV — bot transferred to senior (handoff)"

Summarise ONLY the exchanges below. Output plain text, one line per exchange, no bullet points.

EXCHANGES:
{exchanges}

EXISTING SUMMARY (append to this, do not repeat):
{existing}"""

_CALL_SUMMARY_PROMPT = """\
Summarise this customer service call in 3-5 short lines for internal records.
Format: plain text, one line per key point. No bullets. Be concise.
Include: customer name if known, topics discussed, outcome (resolved/transferred/unknown).

FULL CONVERSATION:
{conversation}"""


class ConversationSummariser:
    def __init__(self, llm, summarise_every: int = SUMMARISE_EVERY):
        self.llm              = llm
        self.summarise_every  = summarise_every
        self.rolling_summary  = ""          # compressed summary of old turns
        self._summarised_up_to = 0          # index into history already summarised
        self._lock            = threading.Lock()

    def _call_plain(self, messages: List[Dict]) -> str:
        """
        Call Groq without response_format=json_object.
        The main llm.complete() hardcodes JSON mode which causes a 400
        when the prompt doesn't ask for JSON output.
        """
        payload = {
            "model":       self.llm.model,
            "messages":    messages,
            "temperature": 0.2,
            "max_tokens":  300,
            "stream":      False,
            # NO response_format here — plain text output
        }
        r = requests.post(
            self.llm.url,
            headers={"Authorization": f"Bearer {self.llm.api_key}",
                     "Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()

    # ─────────────────────────────────────────────────────────────────────────

    def maybe_summarise(self, history: List[Dict]) -> None:
        """
        Called after each turn. If enough new turns have accumulated since
        the last compression, compress them into the rolling summary.
        Runs in a background thread so it doesn't block the bot.
        """
        user_turns_since = sum(
            1 for h in history[self._summarised_up_to:]
            if h["role"] == "user"
        )
        if user_turns_since >= self.summarise_every:
            # Grab the batch to compress before spawning thread
            batch = history[self._summarised_up_to:]
            existing = self.rolling_summary
            idx_end  = len(history)
            threading.Thread(
                target=self._compress,
                args=(batch, existing, idx_end),
                daemon=True,
            ).start()

    def _compress(self, batch: List[Dict], existing: str, idx_end: int) -> None:
        """Background: compress batch into rolling summary."""
        exchanges = "\n".join(
            f"{'Customer' if h['role']=='user' else 'Bot'}: {h['text']}"
            for h in batch
        )
        prompt = _ROLLING_PROMPT.format(
            exchanges=exchanges,
            existing=existing or "(none yet)",
        )
        try:
            result = self._call_plain([
                {"role": "system", "content": "You are a concise call summariser. Output plain text only."},
                {"role": "user",   "content": prompt},
            ])
            with self._lock:
                lines = result.strip().splitlines()
                # Keep only last SUMMARY_MAX_LINES to prevent unbounded growth
                all_lines = (existing.strip().splitlines() if existing else []) + lines
                self.rolling_summary  = "\n".join(all_lines[-SUMMARY_MAX_LINES:])
                self._summarised_up_to = idx_end
        except Exception as e:
            print(f"[Summariser] Compression failed: {e}")

    def get_context_block(self) -> str:
        """Return summary block to inject into LLM system prompt."""
        with self._lock:
            if not self.rolling_summary:
                return ""
            return f"\n\nCALL_SUMMARY_SO_FAR:\n{self.rolling_summary}"

    # ─────────────────────────────────────────────────────────────────────────

    def generate_call_summary(self, history: List[Dict],
                               customer_context: dict) -> str:
        """
        Generate a final human-readable call summary.
        Called on session end (Ctrl+C).
        """
        if not history:
            return "No conversation recorded."

        name = customer_context.get("customer_name", "Unknown")
        conversation = "\n".join(
            f"{'Customer' if h['role']=='user' else 'Bot'}: {h['text']}"
            for h in history
        )
        prompt = _CALL_SUMMARY_PROMPT.format(conversation=conversation)
        try:
            summary = self._call_plain([
                {"role": "system", "content": "You are a concise call summariser. Output plain text only."},
                {"role": "user",   "content": prompt},
            ])
            header = (
                f"Call Summary\n"
                f"============\n"
                f"Customer  : {name}\n"
                f"Date/Time : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"Turns     : {sum(1 for h in history if h['role']=='user')}\n"
                f"------------\n"
            )
            return header + summary.strip()
        except Exception as e:
            return f"Summary generation failed: {e}"

    def save_call_summary(self, history: List[Dict],
                           customer_context: dict,
                           output_dir: str = "./logs/call_summaries") -> Optional[str]:
        """Generate and save call summary to a .txt file. Returns filepath."""
        os.makedirs(output_dir, exist_ok=True)
        name      = customer_context.get("customer_name", "unknown").replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"{timestamp}_{name}.txt"
        filepath  = os.path.join(output_dir, filename)

        summary = self.generate_call_summary(history, customer_context)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(summary)
        return filepath