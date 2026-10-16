"""Optional notification adapters; no credentials are required to import."""
import os
class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None, transport=None):
        self.token = token or os.getenv('SENTINAL_TELEGRAM_TOKEN'); self.chat_id = chat_id or os.getenv('SENTINAL_TELEGRAM_CHAT_ID')
        self.transport = transport
    @property
    def configured(self): return bool(self.token and self.chat_id)
    def send(self, message: str) -> bool:
        if not self.configured: return False
        if self.transport is None: return False  # transport intentionally injected by deployment
        self.transport(self.token, self.chat_id, message)
        return True
