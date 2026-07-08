"""
Enhanced LLM Provider with Async Support
All features configurable via .env file.
"""
import asyncio
import aiohttp
import requests
from typing import List, Dict, Optional
import time


class GroqLLM:
    """
    Enhanced Groq LLM client with async support and retries.
    """
    
    def __init__(
        self,
        enabled: bool = True,
        api_key: str = "",
        model: str = "llama-3.3-70b-versatile",
        temperature: float = 0.2,
        max_tokens: int = 350,
        timeout: float = 60.0,
        max_retries: int = 2,
        enable_async: bool = True,
    ):
        if enabled and not api_key:
            raise RuntimeError('GROQ_API_KEY is missing in .env')
        
        self.enabled = enabled
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.enable_async = enable_async
        self.url = 'https://api.groq.com/openai/v1/chat/completions'
        
        # Stats
        self._stats = {
            "completions": 0,
            "total_tokens": 0,
            "total_time_sec": 0.0,
            "retries": 0,
            "errors": 0,
        }
    
    def complete(self, messages: List[Dict[str, str]]) -> str:
        """
        Complete chat with JSON response format.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
        
        Returns:
            JSON string response
        """
        if not self.enabled:
            # Return minimal valid JSON when disabled
            return '{"intent":"handoff","say":"LLM disabled","script_blocks":["handoff_main"]}'
        
        if self.enable_async:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    return self._complete_sync(messages)
                else:
                    return asyncio.run(self._complete_async(messages))
            except RuntimeError:
                return self._complete_sync(messages)
        else:
            return self._complete_sync(messages)
    
    def _complete_sync(self, messages: List[Dict[str, str]]) -> str:
        """Synchronous completion with retries."""
        start_time = time.time()
        
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'stream': False,
            'response_format': {'type': 'json_object'}
        }
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(
                    self.url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                r.raise_for_status()
                
                response_data = r.json()
                content = response_data['choices'][0]['message']['content']
                
                # Update stats
                processing_time = time.time() - start_time
                self._stats["completions"] += 1
                self._stats["total_time_sec"] += processing_time
                if attempt > 0:
                    self._stats["retries"] += attempt
                
                # Track tokens if available
                if 'usage' in response_data:
                    self._stats["total_tokens"] += response_data['usage'].get('total_tokens', 0)
                
                return content
            
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt  # Exponential backoff
                    print(f"[LLM] Retry {attempt + 1}/{self.max_retries} after {wait_time}s: {e}")
                    time.sleep(wait_time)
        
        # All retries failed
        self._stats["errors"] += 1
        print(f"[LLM] All retries failed: {last_error}")
        raise last_error
    
    async def _complete_async(self, messages: List[Dict[str, str]]) -> str:
        """Async completion with retries."""
        start_time = time.time()
        
        payload = {
            'model': self.model,
            'messages': messages,
            'temperature': self.temperature,
            'max_tokens': self.max_tokens,
            'stream': False,
            'response_format': {'type': 'json_object'}
        }
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                timeout = aiohttp.ClientTimeout(total=self.timeout)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(self.url, headers=headers, json=payload) as response:
                        response.raise_for_status()
                        response_data = await response.json()
                        content = response_data['choices'][0]['message']['content']
                        
                        # Update stats
                        processing_time = time.time() - start_time
                        self._stats["completions"] += 1
                        self._stats["total_time_sec"] += processing_time
                        if attempt > 0:
                            self._stats["retries"] += attempt
                        
                        if 'usage' in response_data:
                            self._stats["total_tokens"] += response_data['usage'].get('total_tokens', 0)
                        
                        return content
            
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt
                    print(f"[LLM] Retry {attempt + 1}/{self.max_retries} after {wait_time}s: {e}")
                    await asyncio.sleep(wait_time)
        
        # All retries failed
        self._stats["errors"] += 1
        print(f"[LLM] All retries failed: {last_error}")
        raise last_error
    
    def get_stats(self) -> dict:
        """Return LLM statistics."""
        stats = self._stats.copy()
        if stats["completions"] > 0:
            stats["avg_time_sec"] = stats["total_time_sec"] / stats["completions"]
        return stats
    
    def reset_stats(self):
        """Reset statistics."""
        self._stats = {
            "completions": 0,
            "total_tokens": 0,
            "total_time_sec": 0.0,
            "retries": 0,
            "errors": 0,
        }
    
    def get_config(self) -> dict:
        """Return current configuration."""
        return {
            "enabled": self.enabled,
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "enable_async": self.enable_async,
        }

    def stream_complete(self, messages: List[Dict[str, str]]):
        """
        Stream tokens from Groq via SSE (Server-Sent Events).
        Yields text strings as they arrive — no response_format=json_object
        since streaming is used for plain-text TTS pipeline only.

        Usage:
            for token in llm.stream_complete(messages):
                buffer += token
        """
        if not self.enabled:
            yield '{"intent":"handoff","say":"LLM disabled"}'
            return

        payload = {
            'model':       self.model,
            'messages':    messages,
            'temperature': self.temperature,
            'max_tokens':  self.max_tokens,
            'stream':      True,
            # NO response_format — plain text stream for TTS pipeline
        }
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type':  'application/json',
        }

        import json as _json
        try:
            r = requests.post(
                self.url,
                headers=headers,
                json=payload,
                stream=True,
                timeout=self.timeout,
            )
            r.raise_for_status()

            for line in r.iter_lines():
                if not line:
                    continue
                line = line.decode('utf-8')
                if line.startswith('data: '):
                    data = line[6:]
                    if data == '[DONE]':
                        break
                    try:
                        chunk = _json.loads(data)
                        delta = chunk['choices'][0]['delta'].get('content', '')
                        if delta:
                            yield delta
                    except Exception:
                        pass

        except Exception as e:
            self._stats['errors'] += 1
            print(f'[LLM] Stream error: {e}')
            raise

    def translate_to_english(self, text: str) -> str:
        """
        Translate any Indian language into English.
        Returns ONLY the translated sentence.
        """

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content":
                        "You are a translator."
                        "Translate the user's sentence into natural English."
                        "Return ONLY the translated sentence."
                        "Do not explain."
                        "Do not answer the question."
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            "temperature": 0,
            "max_tokens": 300,
            "stream": False
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            self.url,
            headers=headers,
            json=payload,
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"].strip()
    
    def translate_from_english(self, text: str, language: str) -> str:
        """
        Translate English into the requested language.
        """

        language_map = {
            "en-IN": "English",
            "hi-IN": "Hindi",
            "te-IN": "Telugu",
            "ta-IN": "Tamil",
            "kn-IN": "Kannada",
            "ml-IN": "Malayalam",
            "mr-IN": "Marathi",
            "bn-IN": "Bengali",
            "gu-IN": "Gujarati",
            "od-IN": "Odia",
            "pa-IN": "Punjabi",
        }

        target_language = language_map.get(language, "English")

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content":
                        f"You are a translator."
                        f"Translate the following English sentence into {target_language}."
                        "Return ONLY the translated sentence."
                        "Do not explain."
                        "Do not answer."
                },
                {
                    "role": "user",
                    "content": text
                }
            ],
            "temperature": 0,
            "max_tokens": 300,
            "stream": False
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            self.url,
            headers=headers,
            json=payload,
            timeout=self.timeout
        )

        response.raise_for_status()

        return response.json()["choices"][0]["message"]["content"].strip()