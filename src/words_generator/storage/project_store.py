from __future__ import annotations

import json
import os
import shutil
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from words_generator.core.word_validator import normalize_word, word_key
from words_generator.models.project import ProjectSettings

PROJECT_FILE = "project.json"
WORDS_FILE = "words.txt"


class ProjectError(RuntimeError):
    """Raised when a project cannot be created, loaded or saved."""


class ProjectStore:
    """Durable local project storage with immediate word appends and checkpoints."""

    def __init__(self, path: Path, settings: ProjectSettings) -> None:
        self.path = path
        self.settings = settings
        self.words_path = path / WORDS_FILE
        self.history_path = path / "history"
        self.state_path = path / "state"
        self.backups_path = path / "backups"
        self._lock = threading.RLock()
        self.word_keys: set[str] = set()
        self._active_session_file: Path | None = None
        self._load_word_keys()

    @classmethod
    def create(cls, path: str | Path, settings: ProjectSettings) -> "ProjectStore":
        project_path = Path(path).expanduser().resolve()
        settings.validate()
        if project_path.exists() and any(project_path.iterdir()):
            raise ProjectError("The selected directory is not empty.")
        project_path.mkdir(parents=True, exist_ok=True)
        for directory in ("history", "state", "backups"):
            (project_path / directory).mkdir(exist_ok=True)
        (project_path / WORDS_FILE).touch(exist_ok=True)
        store = cls(project_path, settings)
        store.save_settings()
        return store

    @classmethod
    def open(cls, path: str | Path) -> "ProjectStore":
        project_path = Path(path).expanduser().resolve()
        config_path = project_path / PROJECT_FILE
        if not config_path.is_file():
            raise ProjectError(f"Could not find {PROJECT_FILE} in the selected directory.")
        try:
            data = json.loads(config_path.read_text(encoding="utf-8"))
            if data.get("schema_version") != 1:
                raise ProjectError("Unsupported project schema version.")
            settings = ProjectSettings.from_dict(data.get("settings", {}))
        except ProjectError:
            raise
        except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ProjectError(f"Could not read project settings: {exc}") from exc
        project_path.joinpath(WORDS_FILE).touch(exist_ok=True)
        for directory in ("history", "state", "backups"):
            (project_path / directory).mkdir(exist_ok=True)
        return cls(project_path, settings)

    @property
    def word_count(self) -> int:
        return len(self.word_keys)

    def _load_word_keys(self) -> None:
        self.word_keys.clear()
        if not self.words_path.exists():
            return
        try:
            with self.words_path.open("r", encoding="utf-8") as stream:
                for line in stream:
                    raw = line.rstrip("\r\n")
                    if not raw.strip():
                        continue
                    try:
                        self.word_keys.add(word_key(normalize_word(raw)))
                    except ValueError:
                        # Keep malformed legacy rows in the file, but do not index them.
                        continue
        except OSError as exc:
            raise ProjectError(f"Could not read words file: {exc}") from exc

    def save_settings(self) -> None:
        self.settings.validate()
        payload = {
            "schema_version": 1,
            "settings": self.settings.to_dict(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._atomic_write(self.path / PROJECT_FILE, json.dumps(payload, ensure_ascii=False, indent=2))

    def update_settings(self, settings: ProjectSettings) -> None:
        settings.validate()
        with self._lock:
            self.settings = settings
            self.save_settings()

    def add_word(self, word: str) -> bool:
        candidate = normalize_word(word)
        key = word_key(candidate)
        with self._lock:
            if key in self.word_keys:
                return False
            try:
                with self.words_path.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(candidate + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
            except OSError as exc:
                raise ProjectError(f"Could not append a word to {WORDS_FILE}: {exc}") from exc
            self.word_keys.add(key)
            return True

    def start_session(self, metadata: dict[str, Any]) -> str:
        session_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S") + "_" + uuid4().hex[:8]
        with self._lock:
            self._active_session_file = self.history_path / f"session_{session_id}.jsonl"
            self.append_event("session_created", {"session_id": session_id, **metadata})
        return session_id

    def append_event(self, event: str, payload: dict[str, Any] | None = None) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "payload": payload or {},
        }
        with self._lock:
            if self._active_session_file is None:
                return
            try:
                with self._active_session_file.open("a", encoding="utf-8", newline="\n") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False) + "\n")
                    stream.flush()
            except OSError as exc:
                raise ProjectError(f"Could not write session history: {exc}") from exc

    def save_checkpoint(self, state: dict[str, Any]) -> None:
        payload = {**state, "updated_at": datetime.now(UTC).isoformat()}
        self._atomic_write(
            self.state_path / "generation_state.json",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def load_checkpoint(self) -> dict[str, Any] | None:
        checkpoint = self.state_path / "generation_state.json"
        if not checkpoint.is_file():
            return None
        try:
            data = json.loads(checkpoint.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ProjectError(f"Could not read generation checkpoint: {exc}") from exc
        return data if isinstance(data, dict) else None

    def finish_session(self, session_id: str, stats: dict[str, Any], elapsed: float) -> None:
        self.append_event(
            "session_summary",
            {"session_id": session_id, "stats": stats, "elapsed_seconds": elapsed},
        )
        self._active_session_file = None

    def create_backup(self) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
        destination = self.backups_path / f"words_{timestamp}.txt"
        try:
            shutil.copy2(self.words_path, destination)
        except OSError as exc:
            raise ProjectError(f"Could not create backup: {exc}") from exc
        return destination

    def list_sessions(self) -> list[Path]:
        return sorted(self.history_path.glob("session_*.jsonl"), reverse=True)

    @staticmethod
    def _atomic_write(path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise ProjectError(f"Could not save {path.name}: {exc}") from exc
