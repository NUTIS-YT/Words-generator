from __future__ import annotations

from words_generator.models.project import DEFAULT_SYSTEM_PROMPT

PROMPT_TEMPLATES: dict[str, tuple[str, str]] = {
    "standard": (
        "Standard",
        DEFAULT_SYSTEM_PROMPT,
    ),
    "strict": (
        "Strict format",
        "You are a vocabulary generator. Return exactly one standalone word, and nothing else. "
        "No quotes, punctuation, numbering, markdown, definitions, translations, or explanations. "
        "The word must match the requested language and part of speech.",
    ),
    "diverse": (
        "Diverse vocabulary",
        "Generate exactly one useful, specific, non-obvious word in the requested language and part "
        "of speech. Prefer variety over the most common beginner vocabulary. Return only the word, "
        "without explanations or formatting.",
    ),
    "rare": (
        "Rare vocabulary",
        "Generate exactly one relatively uncommon but valid word in the requested language and part "
        "of speech. Avoid invented forms. Return only the word, without definitions, translations, "
        "quotes, or any additional text.",
    ),
}


def build_user_prompt(language: str, part_of_speech: str) -> str:
    return (
        f"Generate one {part_of_speech.lower()} in {language}. "
        "Return exactly one word and no other text."
    )


def prompt_for_template(template_id: str, language: str, part_of_speech: str) -> str:
    del language, part_of_speech  # Kept in the signature for future localized templates.
    try:
        return PROMPT_TEMPLATES[template_id][1]
    except KeyError as exc:
        raise ValueError(f"Unknown prompt template: {template_id}") from exc
