from pathlib import Path

from words_generator.core.generator import GenerationEngine
from words_generator.models.project import ProjectSettings
from words_generator.models.sampling import SamplingSettings
from words_generator.storage.project_store import ProjectStore


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = 0

    def generate_word(self, *, system_prompt: str, user_prompt: str, sampling: SamplingSettings) -> str:
        assert "exactly one" in system_prompt.lower()
        assert "english" in user_prompt.lower()
        self.calls += 1
        return next(self.responses)


def test_generator_rejects_duplicates_and_writes_only_unique_words(tmp_path: Path) -> None:
    settings = ProjectSettings(
        name="test",
        target_words=2,
        max_attempts_per_word=5,
        max_request_retries=0,
    )
    store = ProjectStore.create(tmp_path / "project", settings)
    client = FakeClient(["Apple", "apple", "banana."])
    engine = GenerationEngine(client, store, settings)

    stats = engine.run()

    assert stats.status == "completed"
    assert stats.added == 2
    assert stats.duplicates == 1
    assert stats.api_requests == 3
    assert client.calls == 3
    assert (store.path / "words.txt").read_text(encoding="utf-8") == "Apple\nbanana\n"
    checkpoint = store.load_checkpoint()
    assert checkpoint is not None
    assert checkpoint["status"] == "completed"


def test_generator_stops_after_attempt_limit(tmp_path: Path) -> None:
    settings = ProjectSettings(
        name="test",
        target_words=1,
        max_attempts_per_word=2,
        max_request_retries=0,
    )
    store = ProjectStore.create(tmp_path / "project", settings)
    store.add_word("AlreadyExists")
    client = FakeClient(["AlreadyExists", "alreadyexists"])

    stats = GenerationEngine(client, store, settings).run()

    assert stats.status == "stalled"
    assert stats.added == 0
    assert stats.duplicates == 2
