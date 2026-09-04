"""Paths and user settings."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

APP_ID = "org.ubsr.UBSR"
APP_NAME = "UBSR"
APP_TAGLINE = "Union of Black Socialist Republics"


def _xdg(var: str, default: Path) -> Path:
    value = os.environ.get(var)
    return Path(value) if value else default


_override = os.environ.get("UBSR_DATA_DIR")
if _override:
    DATA_DIR = Path(_override)
    CONFIG_DIR = Path(_override)
else:
    DATA_DIR = _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / "ubsr"
    CONFIG_DIR = _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / "ubsr"

MEDIA_DIR = DATA_DIR / "media"
DB_PATH = DATA_DIR / "ubsr.db"
SETTINGS_PATH = CONFIG_DIR / "settings.json"

DEFAULTS: dict = {
    "onboarded": False,
    # AI backend: "anthropic" or "openai_compat"
    "backend": "anthropic",
    "anthropic_api_key": "",
    "anthropic_model": "claude-opus-5",
    "anthropic_effort": "low",
    # OpenAI-compatible servers: Ollama, LM Studio, llama.cpp, OpenRouter, ...
    "openai_base_url": "http://localhost:11434/v1",
    "openai_api_key": "",
    "openai_model": "llama3.1",
    # Optional image generation via a Stable Diffusion WebUI (AUTOMATIC1111) API
    "imagegen_enabled": False,
    "imagegen_url": "http://127.0.0.1:7860",
    "imagegen_steps": 20,
    # Content
    "mature_content": False,
    "age_confirmed": False,
    # How lively the AI world is: "quiet", "normal", "busy"
    "activity_level": "normal",
    "window_width": 1100,
    "window_height": 760,
}


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)


class Settings:
    """A small JSON-backed settings store."""

    def __init__(self, path: Path = SETTINGS_PATH):
        self.path = path
        self._lock = threading.Lock()
        self._data = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                stored = json.load(fh)
            if isinstance(stored, dict):
                self._data.update(stored)
        except (OSError, ValueError):
            pass

    def save(self) -> None:
        ensure_dirs()
        tmp = self.path.with_suffix(".json.tmp")
        with self._lock:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._data, fh, indent=2)
            os.replace(tmp, self.path)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def get(self, key: str, default=None):
        with self._lock:
            return self._data.get(key, DEFAULTS.get(key, default))

    def set(self, key: str, value, save: bool = True) -> None:
        with self._lock:
            self._data[key] = value
        if save:
            self.save()

    def as_dict(self) -> dict:
        with self._lock:
            return dict(self._data)

    # Convenience -----------------------------------------------------
    @property
    def mature(self) -> bool:
        return bool(self.get("mature_content")) and bool(self.get("age_confirmed"))

    def anthropic_key(self) -> str:
        return (self.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY", "")).strip()
