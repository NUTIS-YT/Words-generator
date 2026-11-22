from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal

from words_generator.api.client import APIConfig, OpenAICompatibleClient
from words_generator.core.generator import GenerationEngine
from words_generator.models.generation import GenerationStats
from words_generator.models.project import ProjectSettings
from words_generator.models.sampling import SamplingSettings
from words_generator.storage.project_store import ProjectStore


class GenerationWorker(QThread):
    stats_updated = Signal(object)
    event_logged = Signal(str, object)
    generation_finished = Signal(object)
    worker_error = Signal(str)

    def __init__(
        self,
        store: ProjectStore,
        project_settings: ProjectSettings,
        api_config: APIConfig,
        sampling: SamplingSettings,
    ) -> None:
        super().__init__()
        self.store = store
        self.project_settings = project_settings
        self.api_config = api_config
        self.sampling = sampling
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()

    def request_pause(self) -> None:
        self._pause_event.set()

    def request_resume(self) -> None:
        self._pause_event.clear()

    def request_stop(self) -> None:
        self._stop_event.set()
        self._pause_event.clear()

    def run(self) -> None:
        client = None
        try:
            client = OpenAICompatibleClient(self.api_config)
            settings = ProjectSettings.from_dict(self.project_settings.to_dict())
            settings.sampling = self.sampling
            engine = GenerationEngine(
                client,
                self.store,
                settings,
                stop_event=self._stop_event,
                pause_event=self._pause_event,
                event_callback=lambda event, data: self.event_logged.emit(event, data),
                stats_callback=lambda stats: self.stats_updated.emit(stats.to_dict()),
            )
            result: GenerationStats = engine.run()
            self.generation_finished.emit(result.to_dict())
        except Exception as exc:  # Surface a concise error while keeping the GUI alive.
            self.worker_error.emit(str(exc))
        finally:
            if client is not None:
                client.close()
