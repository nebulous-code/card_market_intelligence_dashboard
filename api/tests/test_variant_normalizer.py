"""
Tests for services.variant_normalizer.

The function is pure -- no DB or fixtures needed. Covers each branch of
the splitting, trimming, blank-handling, and acronym-preservation
rules described in the M04_S02 spec.
"""

from services.variant_normalizer import normalize


def test_none_returns_empty_list():
    assert normalize(None) == []


def test_blank_string_returns_empty_list():
    assert normalize("") == []


def test_whitespace_only_returns_empty_list():
    assert normalize("   \t  ") == []


def test_single_lowercase_word_titlecased():
    assert normalize("holo") == ["Holo"]


def test_multi_word_titlecased():
    assert normalize("reverse holo") == ["Reverse Holo"]


def test_mixed_case_normalized():
    assert normalize("ReVeRSe HoLo") == ["Reverse Holo"]


def test_all_uppercase_word_preserved_as_acronym():
    """The spec explicitly accepts treating any all-caps token as an
    acronym -- ``PSA`` stays ``PSA`` even though ``REVERSE`` would also
    be left alone by the same rule."""
    assert normalize("PSA graded") == ["PSA Graded"]


def test_all_uppercase_multiword_preserved_per_word():
    assert normalize("REVERSE HOLO") == ["REVERSE HOLO"]


def test_internal_whitespace_collapsed():
    assert normalize("reverse    holo") == ["Reverse Holo"]


def test_split_on_comma():
    assert normalize("Reverse Holo, Misprint") == ["Reverse Holo", "Misprint"]


def test_split_on_pipe_slash_ampersand():
    assert normalize("a | b / c & d") == ["A", "B", "C", "D"]


def test_empty_fragments_dropped():
    assert normalize(", , holo, ,") == ["Holo"]


def test_leading_digits_titlecased_after_first_letter():
    """``1st edition holo`` -> ``1st Edition Holo`` -- the first character
    is a digit so the word stays as-is up through the digit and only the
    next letter is uppercased."""
    assert normalize("1st edition holo") == ["1st Edition Holo"]


def test_non_string_coerced_to_string():
    """Excel sometimes returns numbers; we still try to normalize."""
    assert normalize(42) == ["42"]


def test_acronym_with_digits_preserved():
    """``BGS10`` is letters + digits, all letters uppercase -- preserved."""
    assert normalize("BGS10") == ["BGS10"]


def test_word_with_no_letters_left_alone():
    """``42`` has no letters; the all-letters-uppercase check returns
    False (no letters at all), so the title-case branch runs but the
    string is unchanged because there are no letters to lowercase."""
    assert normalize("42 mint") == ["42 Mint"]
