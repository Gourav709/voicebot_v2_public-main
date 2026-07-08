from dataclasses import dataclass, field
from typing import Dict, List, Optional

@dataclass
class ConversationState:
    turn: int = 0
    last_intent: Optional[str] = None
    last_faq_id: Optional[str] = None
    history: List[Dict[str, str]] = field(default_factory=list)
