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
        self.calls += 1
        return next(self.responses)


def test_run_target_counts_only_unique_words_not_api_requests(tmp_path: Path) -> None:
    settings = ProjectSettings(name="test", target_words=2, max_request_retries=0)
    store = ProjectStore.create(tmp_path / "project", settings)
    # An existing word and 18 subsequent variants are duplicates. None of those
    # 19 requests can consume the target: two new unique words must still arrive.
    store.add_word("Apple")
    responses = ["Apple"] + ["apple"] * 18 + ["banana.", "carrot"]
    client = FakeClient(responses)

    stats = GenerationEngine(client, store, settings).run()

    assert stats.status == "completed"
    assert stats.added == 2
    assert stats.duplicates == 19
    assert stats.api_requests == 21
    assert client.calls == 21
    assert (store.path / "words.txt").read_text(encoding="utf-8") == "Apple\nbanana\ncarrot\n"
    checkpoint = store.load_checkpoint()
    assert checkpoint is not None
    assert checkpoint["status"] == "completed"
    assert checkpoint["target_unique_words"] == 2
    assert checkpoint["unique_words_added"] == 2


def test_invalid_responses_do_not_consume_unique_word_target(tmp_path: Path) -> None:
    settings = ProjectSettings(name="test", target_words=1, max_request_retries=0)
    store = ProjectStore.create(tmp_path / "project", settings)
    responses = ["two words"] * 20 + ["valid"]
    client = FakeClient(responses)

    stats = GenerationEngine(client, store, settings).run()

    assert stats.status == "completed"
    assert stats.added == 1
    assert stats.invalid_responses == 20
    assert stats.api_requests == 21
    assert (store.path / "words.txt").read_text(encoding="utf-8") == "valid\n"
