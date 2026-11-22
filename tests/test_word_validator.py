import pytest

from words_generator.core.word_validator import (
    WordValidationError,
    normalize_word,
    word_key,
)


def test_normalizes_outer_quotes_punctuation_and_unicode() -> None:
    assert normalize_word('  “Ｃomputer.”  ') == "Computer"
    assert word_key("Straße") == word_key("STRASSE")


@pytest.mark.parametrize("response", ["", "two words", "word\nother", "word123", "hello🙂", "---"])
def test_rejects_non_single_word_responses(response: str) -> None:
    with pytest.raises(WordValidationError):
        normalize_word(response)


def test_allows_internal_hyphens_and_apostrophes() -> None:
    assert normalize_word("mother-in-law") == "mother-in-law"
    assert normalize_word("l’esprit") == "l’esprit"
