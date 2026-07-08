from dataclasses import dataclass, field
from typing import Any, Dict, List
from datetime import datetime
import os, json

@dataclass
class EventLogger:
    to_file: bool = False
    file_path: str = './logs/events.jsonl'
    events: List[Dict[str, Any]] = field(default_factory=list)

    def log(self, event_type: str, payload: Dict[str, Any]) -> None:
        evt = {'ts': datetime.utcnow().isoformat()+'Z', 'type': event_type, 'payload': payload}
        self.events.append(evt)
        if self.to_file:
            os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
            with open(self.file_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(evt, ensure_ascii=False)+'\n')
