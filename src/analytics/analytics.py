"""Analytics stub."""
class ConversationAnalytics:
    def __init__(self, *args, **kwargs):
        self.enabled = False
    def update_config(self, config): pass
    def increment_turn(self): pass
    def log_user_message(self, text): pass
    def log_bot_message(self, text): pass
    def update_from_component_stats(self, component_name, stats): pass
    def finalize(self): pass
    def get_metrics(self): return {}
    def get_summary(self): return "Analytics disabled"

def create_analytics_from_env(*args, **kwargs):
    return ConversationAnalytics(enabled=False)