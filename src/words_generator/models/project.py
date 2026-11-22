from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from words_generator.models.sampling import SamplingSettings

DEFAULT_SYSTEM_PROMPT = """You are a precise vocabulary generator. Generate exactly one word in the requested language and part of speech. Return only the word, with no numbering, quotation marks, explanations, translations, or additional text. Do not return a phrase or multiple alternatives."""


@dataclass(slots=True)
class ProjectSettings:
    name: str = "Untitled project"
    language: str = "English"
    part_of_speech: str = "Nouns"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    prompt_template: str = "standard"
    target_words: int = 100
    max_attempts_per_word: int = 15
    max_request_retries: int = 3
    sampling: SamplingSettings = field(default_factory=SamplingSettings)
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Project name cannot be empty.")
        if not self.language.strip():
            raise ValueError("Language cannot be empty.")
        if not self.part_of_speech.strip():
            raise ValueError("Part of speech cannot be empty.")
        if not self.system_prompt.strip():
            raise ValueError("System prompt cannot be empty.")
        if not 1 <= self.target_words <= 1_000_000:
            raise ValueError("Target word count must be between 1 and 1,000,000.")
        if not 1 <= self.max_attempts_per_word <= 1000:
            raise ValueError("Max attempts per word must be between 1 and 1000.")
        if not 0 <= self.max_request_retries <= 10:
            raise ValueError("Request retries must be between 0 and 10.")
        self.sampling.validate()

    def to_dict(self) -> dict[str, Any]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectSettings":
        values = dict(data)
        values["sampling"] = SamplingSettings.from_dict(values.get("sampling"))
        allowed = cls.__dataclass_fields__
        instance = cls(**{key: value for key, value in values.items() if key in allowed})
        instance.validate()
        return instance
