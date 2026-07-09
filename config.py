"""Central configuration: supported file types and model defaults."""

from dataclasses import dataclass

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff'}

# Extensions the "by content" mode can actually read and summarize.
TEXT_EXTENSIONS = {'.txt', '.md', '.docx', '.doc', '.pdf', '.xls', '.xlsx', '.csv', '.ppt', '.pptx'}

# Subfolder used by "by type" mode, which sorts on extension alone and so can
# also bucket formats (like ebooks) that content mode can't read yet.
TEXT_TYPE_SUBFOLDERS = {
    '.txt': 'plain_text_files',
    '.md': 'plain_text_files',
    '.doc': 'doc_files',
    '.docx': 'doc_files',
    '.pdf': 'pdf_files',
    '.xls': 'xls_files',
    '.xlsx': 'xls_files',
    '.csv': 'xls_files',
    '.ppt': 'presentation_files',
    '.pptx': 'presentation_files',
    '.epub': 'ebooks',
    '.mobi': 'ebooks',
    '.azw': 'ebooks',
    '.azw3': 'ebooks',
}


@dataclass(frozen=True)
class ModelConfig:
    """Ollama models used for content understanding."""
    vision_model: str = "llava:7b"
    text_model: str = "llama3.2:3b"
    host: str = "http://localhost:11434"


LOG_DIR = "logs"
