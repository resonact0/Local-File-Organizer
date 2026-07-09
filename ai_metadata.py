"""Shared logic for turning a raw AI-generated description into a sanitized
folder name and file name. Used by both image and text content processors
(see image_data_processing.py / text_data_processing.py) to avoid duplicating
the naming/cleanup pipeline for each content type."""

import os
import re
import time
from dataclasses import dataclass

from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
from nltk.tokenize import word_tokenize
from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

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


def process_single_file(file_path, describe_and_name_fn, silent=False):
    """Run `describe_and_name_fn(progress, task_id) -> (foldername, filename, description)`
    under a progress bar, log the outcome, and return it as FileMetadata."""
    start_time = time.time()
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        disable=silent,
    ) as progress:
        task_id = progress.add_task(f"Processing {os.path.basename(file_path)}", total=1.0)
        foldername, filename, description = describe_and_name_fn(progress, task_id)

    logger.info(
        "Processed '%s' in %.2fs -> %s/%s",
        file_path, time.time() - start_time, foldername, filename,
    )
    logger.debug("Description for '%s': %s", file_path, description)

    return FileMetadata(file_path=file_path, foldername=foldername, filename=filename, description=description)
