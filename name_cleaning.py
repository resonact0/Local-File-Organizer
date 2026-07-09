"""Pure-regex cleanup of torrent/release-group junk in folder and file names,
so classification prompts and destination paths see a human-meaningful title
(e.g. "Machine Learning in Python - Essential Techniques (2015) (Pdf, Epub &
Mobi) Gooner" -> "Machine Learning in Python - Essential Techniques")."""

import os
import re

from logging_setup import get_logger

logger = get_logger(__name__)

# Known release-group / scene tags that carry no meaning about the content.
# Matched as whole words anywhere in the name.
_RELEASE_TAGS = frozenset({
    'gooner', 'mantesh', 'ebook-zak', 'wwrg', 'wwt', 'eclipse', 'roflcopter2110',
    'kabooks', 'stormrg', 'b4tman', 'yify', 'rarbg', 'axxo', 'ettv', 'eztv',
    'nogrp', 'bookflare', 'tpb', 'cpul',
})

# "ebook" needs its leading 'e': plain "book(s)" is a real title word
# ("The Book of Books") and must never be treated as a format marker.
_FORMAT_WORDS = r'(?:true\s+)?(?:pdf|epub|mobi|azw3?|djvu|ebooks?)'

# [ECLiPSE], [WWRG], {B4tman} -- bracket/brace segments in shared files are
# essentially always tracker/quality junk, never part of a title.
_BRACKET_SEGMENT = re.compile(r'\[[^\]]*\]|\{[^}]*\}')

# (2017), (Pdf, Epub & Mobi), (2016) (Epub), (True PDF) -- parenthesized
# segments made only of years/format words/separators. Parens carrying real
# content, like "(2nd Edition)", survive.
_JUNK_PARENS = re.compile(
    r'\(\s*(?:(?:19|20)\d{2}|' + _FORMAT_WORDS + r'|[\s,&+/.-])+\s*\)',
    re.IGNORECASE,
)

# Bare format-marker runs outside parens: "True PDF", "Pdf, Epub & Mobi",
# "ePUB MOBI eBOOK".
_FORMAT_MARKERS = re.compile(
    r'\b' + _FORMAT_WORDS + r'\b(?:\s*[,&+/]?\s*\b' + _FORMAT_WORDS + r'\b)*',
    re.IGNORECASE,
)

_RELEASE_TAG_WORDS = re.compile(
    r'\b(?:' + '|'.join(re.escape(tag) for tag in sorted(_RELEASE_TAGS)) + r')\b',
    re.IGNORECASE,
)

# Trailing "- <token>" is only stripped when the token itself looks like junk:
# a known tag or a scene numeric id, e.g. "True PDF - 4055" -> "- 4055".
_TRAILING_TOKEN = re.compile(r'[-–]\s*(\S+)\s*$')
_NUMERIC_ID = re.compile(r'^[A-Za-z]*\d{3,}$')

# Characters not allowed (or unwise) in a single path component.
_UNSAFE_PATH_CHARS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _strip_trailing_junk_tokens(name):
    """Repeatedly drop a trailing '- token' when the token is a release tag
    or a bare numeric id (e.g. '- 4055', '- Gooner')."""
    while True:
        match = _TRAILING_TOKEN.search(name)
        if not match:
            return name
        token = match.group(1).lower()
        if token not in _RELEASE_TAGS and not _NUMERIC_ID.match(token):
            return name
        name = name[:match.start()]


def clean_name(raw):
    """Strip release/format junk from a folder name or file stem, returning a
    space-separated title in its original casing. Falls back to `raw`
    (stripped) if cleaning would leave nothing."""
    name = raw
    # Dots used as word separators (Cool.Book.2019) -- but only when the name
    # has no real spaces, so "Node.js Design Patterns" keeps its dot.
    if ' ' not in name.strip():
        name = re.sub(r'\.+', ' ', name)
    # Underscores are separators in file names essentially always.
    name = re.sub(r'_+', ' ', name)

    name = _BRACKET_SEGMENT.sub(' ', name)
    name = _JUNK_PARENS.sub(' ', name)
    # Tags before format markers, so "eBOOK-ZAK" matches whole rather than
    # having its "eBOOK" half eaten first and leaving "-ZAK" behind.
    name = _RELEASE_TAG_WORDS.sub(' ', name)
    name = _FORMAT_MARKERS.sub(' ', name)
    name = _strip_trailing_junk_tokens(name)

    # Collapse separator debris left behind by the removals.
    # Orphaned punctuation tokens left by removals (e.g. "~ ~"), but keep
    # standalone separators that belong to titles: - – + & ( ) quotes.
    name = re.sub(r'(?<!\S)[^\w\s()\'"&+\-–]+(?!\S)', ' ', name)
    name = re.sub(r'\s*[-–]\s*(?=[-–]|$)', ' ', name)        # dangling dashes
    name = re.sub(r'\s{2,}', ' ', name).strip()
    name = name.strip(' -–,&+.~')

    if not name:
        logger.debug("Cleaning emptied name %r; keeping original", raw)
        return raw.strip()
    return name


def sanitize_path_component(name):
    """Make `name` safe as a single path component: drop filesystem-reserved
    characters, collapse whitespace, trim edge dots/spaces, cap the length."""
    sanitized = _UNSAFE_PATH_CHARS.sub(' ', name)
    sanitized = re.sub(r'\s{2,}', ' ', sanitized).strip().strip('. ')
    return sanitized[:80].strip() or 'unnamed'


def clean_filename(file_path):
    """Cleaned, path-safe filename for a file: cleaned stem + original
    extension (lowercased)."""
    base, ext = os.path.splitext(os.path.basename(file_path))
    return sanitize_path_component(clean_name(base)) + ext.lower()
