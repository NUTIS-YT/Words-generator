from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from words_generator.models.sampling import SamplingSettings

APP_NAME = "WordsGenerator"
KEYRING_SERVICE = "words-generator"
KEYRING_USERNAME = "default"


def config_directory() -> Path:
    if os.name == "nt":
        root = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif os.sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return root / APP_NAME


@dataclass(slots=True)
class AppConfig:
    api_base_url: str = "http://localhost:8080/v1"
    model: str = ""
    timeout_seconds: float = 60.0
    sampling: SamplingSettings = field(default_factory=SamplingSettings)
    recent_projects: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_base_url": self.api_base_url,
            "model": self.model,
            "timeout_seconds": self.timeout_seconds,
            "sampling": self.sampling.to_dict(),
            "recent_projects": self.recent_projects[-10:],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        return cls(
            api_base_url=str(data.get("api_base_url", "http://localhost:8080/v1")),
            model=str(data.get("model", "")),
            timeout_seconds=float(data.get("timeout_seconds", 60.0)),
            sampling=SamplingSettings.from_dict(data.get("sampling")),
            recent_projects=[str(item) for item in data.get("recent_projects", [])],
        )


class AppConfigStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = (path or config_directory()) / "settings.json"

    def load(self) -> AppConfig:
        if not self.path.is_file():
            return AppConfig()
        try:
            return AppConfig.from_dict(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            # Keep the app startable if a user settings file was partially corrupted.
            return AppConfig()

    def save(self, config: AppConfig) -> None:
        config.sampling.validate()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(config.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


class CredentialStore:
    """Thin keyring adapter. Never falls back to storing plaintext credentials."""

    def get_api_key(self) -> str:
        try:
            import keyring

            return keyring.get_password(KEYRING_SERVICE, KEYRING_USERNAME) or ""
        except Exception:
            return ""

    def set_api_key(self, api_key: str) -> bool:
        if not api_key:
            self.delete_api_key()
            return True
        try:
            import keyring

            keyring.set_password(KEYRING_SERVICE, KEYRING_USERNAME, api_key)
            return True
        except Exception:
            return False

    def delete_api_key(self) -> None:
        try:
            import keyring

            keyring.delete_password(KEYRING_SERVICE, KEYRING_USERNAME)
        except Exception:
            # Missing credentials and unavailable desktop keyrings are both harmless.
            pass
