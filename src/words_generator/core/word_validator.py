from __future__ import annotations

import re
import unicodedata

# Unicode letters with optional internal hyphen/apostrophe-separated segments.
_WORD_PATTERN = re.compile(r"^[^\W\d_]+(?:[-'’][^\W\d_]+)*$", re.UNICODE)
_OUTER_PUNCTUATION = " \t\r\n\"'" + chr(96) + ".,;:!?()[]{}<>«»“”‘’"


class WordValidationError(ValueError):
    """The model response is not a single lexical token."""


def normalize_word(raw: str) -> str:
    """Normalize superficial formatting while preserving the original word form."""
    if not isinstance(raw, str):
        raise WordValidationError("Response is not text.")
    candidate = unicodedata.normalize("NFKC", raw).strip()
    candidate = candidate.strip(_OUTER_PUNCTUATION)
    if not candidate:
        raise WordValidationError("The model returned an empty response.")
    if any(character.isspace() for character in candidate):
        raise WordValidationError("The response contains more than one token.")
    if not _WORD_PATTERN.fullmatch(candidate):
        raise WordValidationError("The response contains invalid characters or formatting.")
    return candidate


def word_key(word: str) -> str:
    """Return the comparison key used for case-insensitive deduplication."""
    normalized = unicodedata.normalize("NFKC", word).casefold()
    return normalized.replace("’", "'").replace("ʼ", "'")
