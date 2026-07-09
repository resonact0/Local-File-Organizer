"""Shared logic for turning a raw AI-generated description into a sanitized
folder name and file name. Used by both image and text content processors
(see image_data_processing.py / text_data_processing.py) to avoid duplicating
the naming/cleanup pipeline for each content type."""

import os
import re
from dataclasses import dataclass

from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize

from config import CATEGORY_TAXONOMY
from data_processing_common import sanitize_filename
from logging_setup import get_logger

logger = get_logger(__name__)

_lemmatizer = WordNetLemmatizer()

_COMMON_UNWANTED_WORDS = {
    'the', 'and', 'based', 'generated', 'this', 'is', 'filename', 'file', 'folder', 'output',
    'only', 'below', 'text', 'category', 'summary', 'main', 'subject', 'important', 'details',
    'description', 'depicts', 'show', 'shows', 'display', 'illustrates', 'presents',
    'features', 'provides', 'covers', 'includes', 'demonstrates', 'describes',
    'in', 'on', 'of', 'with', 'by', 'for', 'to', 'from', 'a', 'an', 'as', 'at',
}


@dataclass(frozen=True)
class FileMetadata:
    """AI-derived metadata used to decide where a file should be organized to."""
    file_path: str
    foldername: str
    filename: str
    description: str


def clean_ai_output(text, max_words, extra_unwanted_words=()):
    """Normalize raw model output into a lowercase, underscore-joined phrase,
    stripping filler words, punctuation, digits, and duplicates."""
    unwanted = _COMMON_UNWANTED_WORDS | set(extra_unwanted_words) | set(stopwords.words('english'))

    text = re.sub(r'\.\w{1,4}$', '', text)                     # trailing extension, e.g. ".jpg"
    text = re.sub(r'[^\w\s]', ' ', text)                        # punctuation
    text = re.sub(r'\d+', '', text)                             # digits
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', text.strip())    # camelCase -> words

    words = [w.lower() for w in word_tokenize(text) if w.isalpha()]
    words = [_lemmatizer.lemmatize(w) for w in words]

    seen = set()
    filtered = []
    for word in words:
        if word not in unwanted and word not in seen:
            filtered.append(word)
            seen.add(word)
    return '_'.join(filtered[:max_words])


def _strip_label(text, label):
    return re.sub(rf'^{label}:\s*', '', text, flags=re.IGNORECASE).strip()


def generate_filename(text_inference, prompt, description, extra_unwanted_words, fallback_prefix, source_path):
    """Ask the text model for a filename, falling back to keywords from the description."""
    response = text_inference.create_completion(prompt)
    raw = _strip_label(response['choices'][0]['text'].strip(), 'Filename')

    filename = clean_ai_output(raw, max_words=3, extra_unwanted_words=extra_unwanted_words)
    if not filename or filename.lower() == 'untitled':
        filename = clean_ai_output(description, max_words=3, extra_unwanted_words=extra_unwanted_words)
    if not filename:
        filename = f"{fallback_prefix}_{os.path.splitext(os.path.basename(source_path))[0]}"

    return sanitize_filename(filename, max_words=3)


def generate_foldername(text_inference, prompt, description, extra_unwanted_words, fallback):
    """Ask the text model for a category/folder name, falling back to keywords from the description."""
    response = text_inference.create_completion(prompt)
    raw = _strip_label(response['choices'][0]['text'].strip(), 'Category')

    foldername = clean_ai_output(raw, max_words=2, extra_unwanted_words=extra_unwanted_words)
    if not foldername or foldername.lower() == 'untitled':
        foldername = clean_ai_output(description, max_words=2, extra_unwanted_words=extra_unwanted_words)
    if not foldername:
        foldername = fallback

    return sanitize_filename(foldername, max_words=2)


BROAD_CATEGORY_PROMPT_TEMPLATE = """Classify the following summary into exactly one of these categories: {categories}.
Output only the single category word from the list, nothing else.

Summary: {description}

Category:"""


def generate_broad_category(text_inference, description, categories, fallback='other'):
    """Classify a description into one of a small set of top-level categories."""
    prompt = BROAD_CATEGORY_PROMPT_TEMPLATE.format(categories=', '.join(categories), description=description)
    response = text_inference.create_completion(prompt)
    raw = _strip_label(response['choices'][0]['text'].strip(), 'Category')

    match = re.search(r'[a-zA-Z]+', raw)
    word = match.group(0).lower() if match else ''
    return word if word in categories else fallback


def generate_hierarchical_foldername(text_inference, prompt, description, extra_unwanted_words, fallback, categories):
    """Generate a two-level folder path: a broad category (e.g. 'science')
    over the free-form specific topic from generate_foldername (e.g. 'string_theory')."""
    specific = generate_foldername(text_inference, prompt, description, extra_unwanted_words, fallback)
    broad = generate_broad_category(text_inference, description, categories)
    return broad if specific == broad else f"{broad}/{specific}"


CATEGORY_INDUCTION_PROMPT_TEMPLATE = """Here are short summaries of files found in a directory:

{summaries}

Propose between {min_categories} and {max_categories} broad, single-word, lowercase categories that
together would make sense as top-level folders for organizing these files. Every file should
reasonably fit under one of them. Prefer categories that reflect what is actually described above
over generic ones that don't apply here.
Output only a comma-separated list of the category words, nothing else.

Categories:"""

# Representative sample size for taxonomy induction: enough summaries to see the
# shape of the directory's content without blowing out the prompt on large runs.
CATEGORY_INDUCTION_SAMPLE_SIZE = 40


def induce_category_taxonomy(
    text_inference, descriptions,
    min_categories=4, max_categories=12, fallback=CATEGORY_TAXONOMY,
):
    """Derive a small set of top-level bucket categories from the actual file
    descriptions in this run, instead of always classifying into a fixed list."""
    descriptions = [d for d in descriptions if d and d.strip()]
    if not descriptions:
        return fallback

    sample = descriptions[:CATEGORY_INDUCTION_SAMPLE_SIZE]
    prompt = CATEGORY_INDUCTION_PROMPT_TEMPLATE.format(
        summaries='\n'.join(f"- {d}" for d in sample),
        min_categories=min_categories,
        max_categories=max_categories,
    )
    response = text_inference.create_completion(prompt)
    raw = _strip_label(response['choices'][0]['text'].strip(), 'Categories')

    words = []
    seen = set()
    for match in re.finditer(r'[a-zA-Z]+', raw):
        word = match.group(0).lower()
        if word not in seen:
            seen.add(word)
            words.append(word)
        if len(words) >= max_categories:
            break

    if len(words) < 2:
        logger.warning("Could not induce a category taxonomy from file content; falling back to defaults")
        return fallback

    if 'other' not in words:
        words.append('other')
    return tuple(words)
