import json
from pathlib import Path

class FAQStore:
    def __init__(self, json_path: str):
        self._faqs=json.loads(Path(json_path).read_text(encoding='utf-8'))
    def all(self):
        return self._faqs