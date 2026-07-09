"""File-operation planning and execution: turn file metadata into concrete
copy operations, and carry them out on disk."""

import datetime
import os
import re
import shutil

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from config import IMAGE_EXTENSIONS, TEXT_TYPE_SUBFOLDERS
from logging_setup import get_logger

logger = get_logger(__name__)

_FILENAME_STOPWORDS = re.compile(
    r'\b(jpg|jpeg|png|gif|bmp|txt|md|pdf|docx|xls|xlsx|csv|ppt|pptx|image|picture|photo|this|that|these|those|here|there|'
    r'please|note|additional|notes|folder|name|sure|heres|a|an|the|and|of|in|'
    r'to|for|on|with|your|answer|should|be|only|summary|summarize|text|category)\b',
    flags=re.IGNORECASE,
)


def sanitize_filename(name, max_length=50, max_words=5):
    """Sanitize a filename by stripping unwanted words, punctuation, and length."""
    name = os.path.splitext(name)[0]
    name = _FILENAME_STOPWORDS.sub('', name)
    sanitized = re.sub(r'[^\w\s]', '', name).strip()
    sanitized = re.sub(r'[\s_]+', '_', sanitized).lower().strip('_')

    words = [word for word in sanitized.split('_') if word][:max_words]
    limited_name = '_'.join(words)
    return limited_name[:max_length] if limited_name else 'untitled'


def _build_operation(file_path, dir_path, file_name):
    return {
        'source': file_path,
        'destination': os.path.join(dir_path, file_name),
    }


def process_files_by_date(file_paths, output_path):
    """Plan operations that organize files into year/month folders by modification date."""
    operations = []
    for file_path in file_paths:
        mod_datetime = datetime.datetime.fromtimestamp(os.path.getmtime(file_path))
        dir_path = os.path.join(output_path, mod_datetime.strftime('%Y'), mod_datetime.strftime('%B'))
        operations.append(_build_operation(file_path, dir_path, os.path.basename(file_path)))
    return operations


def _folder_for_type(ext):
    if ext in IMAGE_EXTENSIONS:
        return 'image_files'
    if ext in TEXT_TYPE_SUBFOLDERS:
        return os.path.join('text_files', TEXT_TYPE_SUBFOLDERS[ext])
    return 'others'


def process_files_by_type(file_paths, output_path):
    """Plan operations that organize files into folders by file extension."""
    operations = []
    for file_path in file_paths:
        if os.path.basename(file_path).startswith('.'):
            continue
        ext = os.path.splitext(file_path)[1].lower()
        dir_path = os.path.join(output_path, _folder_for_type(ext))
        operations.append(_build_operation(file_path, dir_path, os.path.basename(file_path)))
    return operations


def compute_operations(metadata_list, output_path, renamed_files, processed_files):
    """Plan copy operations from AI-generated FileMetadata, avoiding name collisions."""
    operations = []
    for metadata in metadata_list:
        if metadata.file_path in processed_files:
            continue
        processed_files.add(metadata.file_path)

        ext = os.path.splitext(metadata.file_path)[1]
        dir_path = os.path.join(output_path, metadata.foldername)

        new_file_name = metadata.filename + ext
        new_file_path = os.path.join(dir_path, new_file_name)
        counter = 1
        while new_file_path in renamed_files:
            new_file_name = f"{metadata.filename}_{counter}{ext}"
            new_file_path = os.path.join(dir_path, new_file_name)
            counter += 1
        renamed_files.add(new_file_path)

        operations.append({
            'source': metadata.file_path,
            'destination': new_file_path,
            'folder_name': metadata.foldername,
            'new_file_name': new_file_name,
        })
    return operations


def execute_operations(operations, dry_run=False, silent=False):
    """Carry out planned copy operations, reporting progress."""
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        transient=True,
        disable=silent,
    ) as progress:
        task = progress.add_task("Organizing Files...", total=len(operations))
        for operation in operations:
            source = operation['source']
            destination = operation['destination']

            if dry_run:
                logger.info("Dry run: would copy '%s' to '%s'", source, destination)
            else:
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                try:
                    shutil.copy2(source, destination)
                    logger.info("Copied '%s' to '%s'", source, destination)
                except OSError as exc:
                    logger.error("Failed to copy '%s' to '%s': %s", source, destination, exc)

            progress.advance(task)
