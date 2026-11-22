from pathlib import Path

from words_generator.core.generator import GenerationEngine
from words_generator.models.project import ProjectSettings
from words_generator.models.sampling import SamplingSettings
from words_generator.storage.project_store import ProjectStore


class FakeClient:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls = 0
        self.requests: list[tuple[str, SamplingSettings]] = []

    def generate_word(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        sampling: SamplingSettings,
    ) -> str:
        self.calls += 1
        self.requests.append((user_prompt, sampling))
        return next(self.responses)


def _alphabetic_word(index: int) -> str:
    letters = []
    while True:
        index, remainder = divmod(index, 26)
        letters.append(chr(ord("a") + remainder))
        if index == 0:
            break
    return "entry" + "".join(reversed(letters))


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


def test_duplicate_loop_updates_prompt_and_temporarily_increases_temperature(
    tmp_path: Path,
) -> None:
    settings = ProjectSettings(
        name="test",
        target_words=2,
        max_request_retries=0,
        context_memory_enabled=True,
        sampling=SamplingSettings(temperature=0.0),
    )
    store = ProjectStore.create(tmp_path / "project", settings)
    # Put the duplicate outside the bounded recent-word window. It must be added
    # to the session exclusion list as soon as the model repeats it.
    store.add_word("apple")
    for index in range(80):
        store.add_word(_alphabetic_word(index))

    assert "apple" not in [word.casefold() for word in store.recent_words]
    client = FakeClient(["apple", "apple", "banana", "pear"])

    stats = GenerationEngine(client, store, settings).run()

    assert stats.status == "completed"
    assert stats.added == 2
    assert stats.duplicates == 2
    assert stats.api_requests == 4

    first_prompt, second_prompt, third_prompt, _fourth_prompt = [
        request[0] for request in client.requests
    ]
    assert "apple" not in first_prompt.casefold()
    assert "apple" in second_prompt.casefold()
    assert client.requests[0][1].temperature == 0.0
    assert client.requests[1][1].temperature == 0.0
    assert client.requests[2][1].temperature == 0.2
    # Accepting a new unique word resets the adaptive sampler to project settings.
    assert client.requests[3][1].temperature == 0.0



def test_existing_words_are_sent_only_when_context_memory_is_enabled(tmp_path: Path) -> None:
    for enabled in (False, True):
        project_path = tmp_path / ("enabled" if enabled else "disabled")
        settings = ProjectSettings(
            name="test",
            target_words=1,
            max_request_retries=0,
            context_memory_enabled=enabled,
        )
        store = ProjectStore.create(project_path, settings)
        store.add_word("knownword")
        client = FakeClient(["brandnew"])

        stats = GenerationEngine(client, store, settings).run()

        assert stats.status == "completed"
        assert stats.added == 1
        prompt = client.requests[0][0]
        assert ("knownword" in prompt.casefold()) is enabled
