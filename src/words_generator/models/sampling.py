from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(slots=True)
class SamplingSettings:
    temperature: float = 0.9
    top_p: float = 0.95
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    max_tokens: int = 24

    def validate(self) -> None:
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("Temperature must be between 0 and 2.")
        if not 0.0 < self.top_p <= 1.0:
            raise ValueError("Top P must be greater than 0 and at most 1.")
        if not -2.0 <= self.frequency_penalty <= 2.0:
            raise ValueError("Frequency penalty must be between -2 and 2.")
        if not -2.0 <= self.presence_penalty <= 2.0:
            raise ValueError("Presence penalty must be between -2 and 2.")
        if not 1 <= self.max_tokens <= 4096:
            raise ValueError("Max tokens must be between 1 and 4096.")

    def to_dict(self) -> dict[str, float | int]:
        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object] | None) -> "SamplingSettings":
        if not data:
            return cls()
        fields = cls.__dataclass_fields__
        values = {key: data[key] for key in fields if key in data}
        instance = cls(**values)
        instance.validate()
        return instance
