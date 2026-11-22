from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from words_generator.api.client import APIConfig, APIError, OpenAICompatibleClient


class ApiTestWorker(QThread):
    completed = Signal(object)
    failed = Signal(str)

    def __init__(self, config: APIConfig) -> None:
        super().__init__()
        self.config = config

    def run(self) -> None:
        client = None
        try:
            client = OpenAICompatibleClient(self.config)
            models = client.list_models()
            self.completed.emit(models)
        except (APIError, ValueError) as exc:
            self.failed.emit(str(exc))
        finally:
            if client is not None:
                client.close()
