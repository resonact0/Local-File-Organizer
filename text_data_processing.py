"""Generate folder/file names for text-based files by summarizing them with
a text model, then naming them from that summary.

Summarizing and naming are separate passes (describe_text_files then
name_text_files) so the caller can induce a content-derived category
taxonomy from all descriptions -- text and image alike -- before any
foldername is decided."""

import time

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from ai_metadata import FileMetadata, generate_filename, generate_hierarchical_foldername
from logging_setup import get_logger

logger = get_logger(__name__)

TEXT_UNWANTED_WORDS = {
    'document', 'key', 'information', 'note', 'notes', 'ideas', 'concepts',
    'i', 'we', 'you', 'they', 'he', 'she', 'it', 'that', 'which', 'are', 'were', 'was', 'be',
    'have', 'has', 'had', 'do', 'does', 'did', 'but', 'if', 'or', 'because', 'about', 'into',
    'through', 'during', 'before', 'after', 'above', 'any', 'each', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'nor', 'not', 'own', 'same', 'so', 'than', 'too', 'very',
    's', 't', 'can', 'will', 'just', 'don', 'should', 'now', 'new', 'discusses',
}

SUMMARY_PROMPT_TEMPLATE = """Provide a concise and accurate summary of the following text, focusing on the main ideas and key details.
Limit your summary to a maximum of 150 words.

Text: {text}

Summary:"""

FILENAME_PROMPT_TEMPLATE = """Based on the summary below, generate a specific and descriptive filename that captures the essence of the document.
Limit the filename to a maximum of 3 words. Use nouns and avoid starting with verbs like 'depicts', 'shows', 'presents', etc.
Do not include any data type words like 'text', 'document', 'pdf', etc. Use only letters and connect words with underscores.

Summary: {description}

Examples:
1. Summary: A research paper on the fundamentals of string theory.
   Filename: fundamentals_of_string_theory

2. Summary: An article discussing the effects of climate change on polar bears.
   Filename: climate_change_polar_bears

Now generate the filename.

Output only the filename, without any additional text.

Filename:"""

FOLDERNAME_PROMPT_TEMPLATE = """Based on the summary below, generate a general category or theme that best represents the main subject of this document.
This will be used as the folder name. Limit the category to a maximum of 2 words. Use nouns and avoid verbs.
Do not include specific details, words from the filename, or any generic terms like 'untitled' or 'unknown'.

Summary: {description}

Examples:
1. Summary: A research paper on the fundamentals of string theory.
   Category: physics

2. Summary: An article discussing the effects of climate change on polar bears.
   Category: environment

Now generate the category.

Output only the category, without any additional text.

Category:"""


def _summarize(text, text_inference):
    prompt = SUMMARY_PROMPT_TEMPLATE.format(text=text)
    response = text_inference.create_completion(prompt)
    return response['choices'][0]['text'].strip()


def describe_text_files(text_tuples, text_inference, silent=False):
    """Summarize each (file_path, text) tuple, returning [(path, description), ...]."""
    results = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        disable=silent,
    ) as progress:
        task_id = progress.add_task("Summarizing documents", total=len(text_tuples) or 1)
        for file_path, text in text_tuples:
            start_time = time.time()
            description = _summarize(text, text_inference)
            logger.info("Summarized '%s' in %.2fs", file_path, time.time() - start_time)
            logger.debug("Description for '%s': %s", file_path, description)
            results.append((file_path, description))
            progress.update(task_id, advance=1)
    return results


def name_text_file(file_path, description, text_inference, categories):
    """Generate (foldername, filename) for an already-summarized document."""
    filename = generate_filename(
        text_inference,
        FILENAME_PROMPT_TEMPLATE.format(description=description),
        description,
        TEXT_UNWANTED_WORDS,
        fallback_prefix='document',
        source_path=file_path,
    )
    foldername = generate_hierarchical_foldername(
        text_inference,
        FOLDERNAME_PROMPT_TEMPLATE.format(description=description),
        description,
        TEXT_UNWANTED_WORDS,
        fallback='documents',
        categories=categories,
    )
    return FileMetadata(file_path=file_path, foldername=foldername, filename=filename, description=description)


def name_text_files(text_descriptions, text_inference, categories, silent=False):
    """Name each summarized document, returning a list of FileMetadata."""
    metadata = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        disable=silent,
    ) as progress:
        task_id = progress.add_task("Naming documents", total=len(text_descriptions) or 1)
        for file_path, description in text_descriptions:
            file_metadata = name_text_file(file_path, description, text_inference, categories)
            logger.info("Named '%s' -> %s/%s", file_path, file_metadata.foldername, file_metadata.filename)
            metadata.append(file_metadata)
            progress.update(task_id, advance=1)
    return metadata
