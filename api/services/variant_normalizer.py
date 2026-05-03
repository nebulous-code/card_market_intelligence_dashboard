"""
Pure variant normalization for the user collection upload flow.

The Variant column on the upload template is free-form text. The user
might type ``reverse holo``, ``REVERSE HOLO``, ``Reverse Holo, Misprint``,
``1st edition holo``, or anything else they like. This module turns that
input into a stable, comparable list of variant labels without calling
any external API. The dashboard variant slicer (M04_S04) groups by these
normalized strings, so consistency matters more than picking the
"correct" capitalization.

Rules:

1. Split on ``,``, ``|``, ``/``, and ``&``. Each fragment becomes its own
   variant.
2. Strip leading/trailing whitespace and collapse internal runs of
   whitespace to a single space.
3. Title-case each remaining word, but preserve any token that the user
   typed entirely in uppercase. This keeps acronyms like ``PSA`` or
   ``BGS`` intact while still cleaning up sloppy ``reverse holo`` /
   ``REVERSE HOLO`` input.
4. Drop empty fragments.

The function is pure (no I/O, no logging, no DB) so the validator and the
endpoint can both call it without side effects.
"""

from __future__ import annotations

import re

# Any of these characters is treated as a separator between variants.
_SEPARATOR_PATTERN = re.compile(r"[,|/&]")
_WHITESPACE_RUN = re.compile(r"\s+")


def normalize(raw: str | None) -> list[str]:
    """Return the normalized list of variants for one cell value.

    A blank or whitespace-only input returns ``[]`` so the caller can
    treat "no variant" uniformly.
    """
    if raw is None:
        return []
    text = str(raw).strip()
    if not text:
        return []

    fragments = _SEPARATOR_PATTERN.split(text)
    out: list[str] = []
    for fragment in fragments:
        cleaned = _normalize_fragment(fragment)
        if cleaned:
            out.append(cleaned)
    return out


def _normalize_fragment(fragment: str) -> str:
    """Trim, collapse whitespace, and apply acronym-preserving Title Case."""
    trimmed = _WHITESPACE_RUN.sub(" ", fragment.strip())
    if not trimmed:
        return ""
    words = trimmed.split(" ")
    return " ".join(_format_word(w) for w in words)


def _format_word(word: str) -> str:
    """Preserve all-uppercase tokens; otherwise apply Title Case.

    A token is considered "all uppercase" when at least one of its
    characters is a letter and every letter in it is uppercase. Numbers
    and punctuation are ignored for the check (so ``1ST`` stays ``1ST``).
    Mixed-case tokens (``Holo``, ``misprint``) get a single Title Case
    pass: first character upper, rest lower.
    """
    if not word:
        return word
    letters = [c for c in word if c.isalpha()]
    if letters and all(c.isupper() for c in letters):
        return word
    return word[:1].upper() + word[1:].lower()
