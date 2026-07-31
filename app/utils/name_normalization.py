"""
Name normalization utilities for Entity Resolution, with specific handling
for Nigerian naming conventions (compound names, honorifics, common
transliteration variants) carried over from the earlier Nigeria
Intelligence Platform entity-resolution work.
"""
from __future__ import annotations

import re
import unicodedata

HONORIFIC_PREFIXES = {
    "mr", "mrs", "miss", "ms", "dr", "prof", "professor", "engr", "engineer",
    "barr", "barrister", "chief", "alhaji", "alhaja", "hajia", "hon", "honorable",
    "sen", "senator", "gov", "governor", "amb", "ambassador", "rev", "reverend",
    "pastor", "imam", "sheikh", "otunba", "oba", "obi", "emir", "sir", "lady",
}

# Common Nigerian name spelling variants that should normalize to the same key.
TRANSLITERATION_MAP = {
    "muhammed": "muhammad", "mohammed": "muhammad", "mohammad": "muhammad", "muhammad": "muhammad",
    "muhammadu": "muhammad", "mohamed": "muhammad",
    "abdullahi": "abdullahi", "abdulahi": "abdullahi", "abdullai": "abdullahi",
    "chukwuemeka": "chukwuemeka", "chukwuemeka's": "chukwuemeka",
    "olusegun": "olusegun", "olusegan": "olusegun",
    "ibrahim": "ibrahim", "ibrahiim": "ibrahim",
    "oluwaseun": "oluwaseun", "oluwaseyi": "oluwaseyi",
}

_WHITESPACE_RE = re.compile(r"\s+")
_NON_ALPHA_RE = re.compile(r"[^a-z0-9\s]")


def strip_diacritics(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def normalize_person_name(raw_name: str) -> str:
    """
    Produces a normalized key suitable for entity-resolution matching:
    lowercased, diacritics stripped, honorifics removed, punctuation
    stripped, whitespace collapsed, common spelling variants unified,
    and tokens sorted so word-order differences ("Ibrahim Musa" vs
    "Musa Ibrahim") still match.
    """
    if not raw_name or not raw_name.strip():
        return ""

    text = strip_diacritics(raw_name.lower())
    text = _NON_ALPHA_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    tokens = [t for t in text.split(" ") if t and t not in HONORIFIC_PREFIXES]
    tokens = [TRANSLITERATION_MAP.get(t, t) for t in tokens]
    tokens.sort()

    return " ".join(tokens)


def normalize_organization_name(raw_name: str) -> str:
    """Normalizes org names: lowercase, strip common legal suffixes, collapse whitespace."""
    if not raw_name or not raw_name.strip():
        return ""

    text = strip_diacritics(raw_name.lower())
    text = _NON_ALPHA_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()

    legal_suffixes = {"ltd", "limited", "plc", "inc", "incorporated", "llc", "corp", "corporation", "company", "co"}
    tokens = [t for t in text.split(" ") if t and t not in legal_suffixes]

    return " ".join(tokens)


def normalize_entity_name(raw_name: str, entity_type: str) -> str:
    if entity_type == "person":
        return normalize_person_name(raw_name)
    if entity_type == "organization":
        return normalize_organization_name(raw_name)
    # Locations, vessels, IPs, domains, emails, phones: lowercase + whitespace collapse is sufficient.
    text = strip_diacritics(raw_name.lower()).strip()
    return _WHITESPACE_RE.sub(" ", text)


def name_similarity(name_a: str, name_b: str) -> float:
    """
    Token-overlap similarity (Jaccard) between two already-normalized names.
    Cheap, dependency-free, and adequate for surfacing merge candidates for
    human review -- not intended as a definitive automatic-merge trigger.
    """
    tokens_a, tokens_b = set(name_a.split()), set(name_b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)