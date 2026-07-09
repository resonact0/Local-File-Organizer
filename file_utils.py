"""Filesystem helpers: walking directories, reading file contents, and
rendering directory trees."""

import os

import docx
import fitz  # PyMuPDF
import pandas as pd
from pptx import Presentation

from config import IMAGE_EXTENSIONS, TEXT_EXTENSIONS
from logging_setup import get_logger

logger = get_logger(__name__)


def read_text_file(file_path, max_chars=3000):
    """Read up to `max_chars` of a plain text file."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as file:
            return file.read(max_chars)
    except OSError as exc:
        logger.error("Error reading text file %s: %s", file_path, exc)
        return None


def read_docx_file(file_path):
    """Read text content from a .docx or .doc file."""
    try:
        doc = docx.Document(file_path)
        return '\n'.join(para.text for para in doc.paragraphs)
    except Exception as exc:
        logger.error("Error reading DOCX file %s: %s", file_path, exc)
        return None


def read_pdf_file(file_path, max_pages=3):
    """Read text content from the first `max_pages` pages of a PDF."""
    try:
        doc = fitz.open(file_path)
        pages = [doc.load_page(i).get_text() for i in range(min(max_pages, len(doc)))]
        return '\n'.join(pages)
    except Exception as exc:
        logger.error("Error reading PDF file %s: %s", file_path, exc)
        return None


def read_spreadsheet_file(file_path):
    """Read text content from an Excel or CSV file."""
    try:
        df = pd.read_csv(file_path) if file_path.lower().endswith('.csv') else pd.read_excel(file_path)
        return df.to_string()
    except Exception as exc:
        logger.error("Error reading spreadsheet file %s: %s", file_path, exc)
        return None


def read_ppt_file(file_path):
    """Read text content from a PowerPoint file."""
    try:
        prs = Presentation(file_path)
        full_text = [
            shape.text for slide in prs.slides for shape in slide.shapes if hasattr(shape, "text")
        ]
        return '\n'.join(full_text)
    except Exception as exc:
        logger.error("Error reading PowerPoint file %s: %s", file_path, exc)
        return None


_READERS_BY_EXTENSION = {
    '.txt': read_text_file,
    '.md': read_text_file,
    '.docx': read_docx_file,
    '.doc': read_docx_file,
    '.pdf': read_pdf_file,
    '.xls': read_spreadsheet_file,
    '.xlsx': read_spreadsheet_file,
    '.csv': read_spreadsheet_file,
    '.ppt': read_ppt_file,
    '.pptx': read_ppt_file,
}


def read_file_data(file_path):
    """Read content from a file based on its extension, or None if unsupported."""
    ext = os.path.splitext(file_path.lower())[1]
    reader = _READERS_BY_EXTENSION.get(ext)
    return reader(file_path) if reader else None


def display_directory_tree(path):
    """Print a directory tree similar to the `tree` command, prefixed by the full path."""
    def tree(dir_path, prefix=''):
        contents = sorted(c for c in os.listdir(dir_path) if not c.startswith('.'))
        pointers = ['├── '] * (len(contents) - 1) + ['└── '] if contents else []
        for pointer, name in zip(pointers, contents):
            full_path = os.path.join(dir_path, name)
            print(prefix + pointer + name)
            if os.path.isdir(full_path):
                extension = '│   ' if pointer == '├── ' else '    '
                tree(full_path, prefix + extension)

    print(os.path.abspath(path))
    if os.path.isdir(path):
        tree(path)


def collect_file_paths(base_path):
    """Collect all file paths under `base_path` (or itself, if it's a file),
    excluding hidden files."""
    if os.path.isfile(base_path):
        return [base_path]

    file_paths = []
    for root, _, files in os.walk(base_path):
        file_paths.extend(os.path.join(root, name) for name in files if not name.startswith('.'))
    return file_paths


def separate_files_by_type(file_paths):
    """Split file paths into (image_files, text_files) based on extension."""
    image_files, text_files = [], []
    for fp in file_paths:
        ext = os.path.splitext(fp.lower())[1]
        if ext in IMAGE_EXTENSIONS:
            image_files.append(fp)
        elif ext in TEXT_EXTENSIONS:
            text_files.append(fp)
    return image_files, text_files
