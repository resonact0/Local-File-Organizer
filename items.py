"""Turns raw file paths into "items" -- the unit content mode organizes -- and
turns categorized items back into copy/move operations.

An item is either one trusted top-level folder (kept intact as a unit, e.g. a
book folder with its pdf/epub/cover) or one loose/untrusted file. Each item
carries the best cheap signals available about its subject matter; taxonomy.py
turns those into descriptions and categories."""

import os
from dataclasses import dataclass, field

from file_utils import (
    read_epub_metadata,
    read_file_data,
    separate_files_by_type,
    split_by_folder_trust,
)
from image_data_processing import describe_image_files
from logging_setup import get_logger
from name_cleaning import clean_filename, clean_name, sanitize_path_component

logger = get_logger(__name__)

# How much of a readable file's text the description prompt sees.
TEXT_EXCERPT_CHARS = 1500
# How many example filenames represent a trusted folder's contents.
FOLDER_SAMPLE_FILES = 5


@dataclass
class Item:
    """One unit of organization: a trusted top-level folder, or one loose file."""
    kind: str            # 'folder' | 'text' | 'image' | 'unreadable'
    source: str          # the top-level folder path, or the file path
    files: list          # every file path belonging to this item
    cleaned_name: str    # junk-stripped folder name / file stem
    signals: str         # "Item information" block for the description prompt
    description: str = ''
    category: str = ''


def _group_by_top_folder(trusted_files, input_path):
    """Group trusted files by the first path component under input_path (e.g.
    the book folder in `book_title/book_title.pdf`), so every file under one
    top-level folder shares a single item and category decision."""
    groups = {}
    for fp in trusted_files:
        rel_path = os.path.relpath(fp, input_path)
        top_dir = rel_path.split(os.sep)[0]
        groups.setdefault(top_dir, []).append(fp)
    return groups


def _folder_item(top_dir, files, input_path):
    cleaned = clean_name(top_dir)
    largest = sorted(files, key=os.path.getsize, reverse=True)[:FOLDER_SAMPLE_FILES]
    stems = [clean_name(os.path.splitext(os.path.basename(fp))[0]) for fp in largest]
    signals = (
        f"Folder name: {cleaned}\n"
        f"Some files inside: {'; '.join(stems)}"
    )
    return Item(kind='folder', source=os.path.join(input_path, top_dir),
                files=files, cleaned_name=cleaned, signals=signals)


def _text_item(fp):
    """Item for a readable loose file; None if the read fails (the caller
    demotes it to an unreadable item instead of dropping it)."""
    content = read_file_data(fp)
    if content is None or not content.strip():
        return None
    cleaned = clean_name(os.path.splitext(os.path.basename(fp))[0])
    signals = (
        f"File name: {cleaned}\n"
        f"Beginning of the file's text:\n{content[:TEXT_EXCERPT_CHARS]}"
    )
    return Item(kind='text', source=fp, files=[fp], cleaned_name=cleaned, signals=signals)


def _unreadable_item(fp):
    """Item for a file whose content can't be read (ebooks, archives...):
    classify from the cleaned filename, plus embedded metadata for epubs."""
    cleaned = clean_name(os.path.splitext(os.path.basename(fp))[0])
    metadata_line = "Embedded metadata: none"
    if fp.lower().endswith('.epub'):
        meta = read_epub_metadata(fp)
        if meta and (meta['title'] or meta['creator'] or meta['subjects']):
            parts = []
            if meta['title']:
                parts.append(f"title={meta['title']}")
            if meta['creator']:
                parts.append(f"author={meta['creator']}")
            if meta['subjects']:
                parts.append(f"subjects={', '.join(meta['subjects'])}")
            metadata_line = f"Embedded metadata: {'; '.join(parts)}"
    signals = f"File name: {cleaned}\n{metadata_line}"
    return Item(kind='unreadable', source=fp, files=[fp], cleaned_name=cleaned, signals=signals)


def _image_item(fp, vision_description):
    cleaned = clean_name(os.path.splitext(os.path.basename(fp))[0])
    signals = (
        f"File name: {cleaned}\n"
        f"What the image shows: {vision_description}"
    )
    return Item(kind='image', source=fp, files=[fp], cleaned_name=cleaned, signals=signals)


def build_items(file_paths, input_path, image_inference, silent=False):
    """Build the item list for a run: one item per trusted top-level folder,
    one per loose/untrusted file (with vision descriptions for images)."""
    if os.path.isdir(input_path):
        trusted_files, untrusted_files = split_by_folder_trust(file_paths, input_path)
    else:
        trusted_files, untrusted_files = [], list(file_paths)
    if trusted_files:
        logger.info("Keeping %d file(s) grouped in their existing named folders", len(trusted_files))

    items = [
        _folder_item(top_dir, files, input_path)
        for top_dir, files in _group_by_top_folder(trusted_files, input_path).items()
    ]

    image_files, text_files, other_files = separate_files_by_type(untrusted_files)

    for fp in text_files:
        item = _text_item(fp)
        if item is None:
            logger.warning("Could not read text content of %s; classifying by filename only", fp)
            item = _unreadable_item(fp)
        items.append(item)

    for fp in other_files:
        items.append(_unreadable_item(fp))

    for fp, description in describe_image_files(image_files, image_inference, silent=silent):
        items.append(_image_item(fp, description))

    folder_count = sum(1 for it in items if it.kind == 'folder')
    loose_count = len(items) - folder_count
    logger.info(
        "Built %d item(s): %d folder, %d loose file",
        len(items), folder_count, loose_count,
    )
    logger.info(
        "%d folder(s) kept intact as a single item each; %d loose file(s) will each get "
        "their own description call -- this loose-file count is what drives runtime, "
        "roughly loose_count x (a few seconds to ~1 minute per item depending on file size).",
        folder_count, loose_count,
    )
    return items


def _unique(destination, used_destinations):
    """Suffix `destination` with _1, _2... (before any extension) until unused."""
    base, ext = os.path.splitext(destination)
    counter = 1
    while destination in used_destinations:
        destination = f"{base}_{counter}{ext}"
        counter += 1
    used_destinations.add(destination)
    return destination


def build_operations(items, output_path, input_path):
    """Plan {'source', 'destination'} operations: folder items mirror their
    inner structure under output/<category>/<cleaned folder name>/, loose
    files land at output/<category>/<cleaned filename>. No AI renaming."""
    operations = []
    used_destinations = set()

    for item in items:
        category = item.category or 'other'
        if item.kind == 'folder':
            folder_dest = _unique(
                os.path.join(output_path, category, sanitize_path_component(item.cleaned_name)),
                used_destinations,
            )
            for fp in item.files:
                rel_path = os.path.relpath(fp, item.source)
                operations.append({'source': fp, 'destination': os.path.join(folder_dest, rel_path)})
        else:
            destination = _unique(
                os.path.join(output_path, category, clean_filename(item.source)),
                used_destinations,
            )
            operations.append({'source': item.source, 'destination': destination})
    return operations
