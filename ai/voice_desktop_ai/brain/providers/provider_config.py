from dataclasses import dataclass, field
import os
from pathlib import Path

from brain.providers.grok_visual_brain import DEFAULT_MODEL


@dataclass(frozen=True)
class ProviderConfig:
    provider: str = "xai"
    model: str = DEFAULT_MODEL
    _api_key: str = field(default="", repr=False)

    @property
    def configured(self):
        return bool(self._api_key)

    @property
    def api_key(self):
        """Internal credential access for a provider constructor; never log this value."""
        return self._api_key

    def safe_status(self):
        return {"provider": self.provider, "configured": self.configured, "model": self.model}


def load_provider_config(environ=None):
    if environ is None:
        try:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[2] / ".env")
        except ImportError:
            pass
        values = os.environ
    else:
        values = environ
    api_key = str(values.get("XAI_API_KEY", "")).strip()
    model = str(values.get("XAI_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL
    return ProviderConfig(model=model, _api_key=api_key)