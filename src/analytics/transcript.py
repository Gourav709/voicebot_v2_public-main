"""Transcript stub."""
class ConversationTranscript:
    def __init__(self, *args, **kwargs):
        self.enabled = False
    def log_user_message(self, text): pass
    def log_bot_message(self, text): pass
    def finalize(self): pass
    def get_filepath(self): return None
    def get_session_info(self): return {"enabled": False}

def create_transcript_from_env(*args, **kwargs):
    return ConversationTranscript(enabled=False)