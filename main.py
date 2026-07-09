"""Entry point: interactively (or via CLI args) organize a directory of files
by content, date, or type, using local Ollama models for content understanding."""

import os
import sys
import time

import cli
from config import LOG_DIR, ModelConfig
from data_processing_common import (
    compute_operations,
    execute_operations,
    process_files_by_date,
    process_files_by_type,
)
from file_utils import (
    collect_file_paths,
    display_directory_tree,
    read_file_data,
    separate_files_by_type,
    split_by_folder_trust,
)
from image_data_processing import process_image_files
from logging_setup import configure_logging, get_logger
from models import load_models
from text_data_processing import process_text_files

logger = get_logger(__name__)


def ensure_nltk_data():
    """Ensure required NLTK corpora are downloaded, quietly."""
    import nltk
    for resource in ('stopwords', 'punkt', 'punkt_tab', 'wordnet'):
        nltk.download(resource, quiet=True)


def _mirror_operations(trusted_files, input_path, output_path):
    """Build operations that keep already-well-organized files exactly where
    their existing folder structure puts them, relative to output_path."""
    operations = []
    for fp in trusted_files:
        rel_path = os.path.relpath(fp, input_path)
        operations.append({
            'source': fp,
            'destination': os.path.join(output_path, rel_path),
            'link_type': 'hardlink',
        })
    return operations


def organize_by_content(file_paths, input_path, output_path, models, silent):
    """Plan operations for 'by content' mode using AI-generated metadata.

    Files that already sit inside a meaningfully-named subfolder (e.g.
    `author/book_title/book_title.pdf` + its cover image) are mirrored as-is
    instead of being reclassified, since splitting them apart by file type
    would break up an already-organized unit. Only files with no such
    context (loose in the input root, or under a generic/junk folder name
    like "Downloads" or "IMG_1234") go through AI classification.
    """
    if os.path.isdir(input_path):
        trusted_files, untrusted_files = split_by_folder_trust(file_paths, input_path)
    else:
        trusted_files, untrusted_files = [], file_paths
    if trusted_files:
        logger.info("Keeping %d file(s) as-is (already organized in named folders)", len(trusted_files))

    image_files, text_files = separate_files_by_type(untrusted_files)

    text_tuples = []
    for fp in text_files:
        content = read_file_data(fp)
        if content is None:
            logger.warning("Unsupported or unreadable text file format: %s", fp)
            continue
        text_tuples.append((fp, content))

    image_metadata = process_image_files(image_files, models.image_inference, models.text_inference, silent=silent)
    text_metadata = process_text_files(text_tuples, models.text_inference, silent=silent)

    operations = _mirror_operations(trusted_files, input_path, output_path)
    operations += compute_operations(image_metadata + text_metadata, output_path, renamed_files=set(), processed_files=set())
    return operations


MODE_HANDLERS = {
    'date': process_files_by_date,
    'type': process_files_by_type,
}


def plan_operations(mode, file_paths, input_path, output_path, models_holder, silent):
    """Compute the operations for the selected mode, lazily loading models for 'content' mode."""
    if mode == 'content':
        if models_holder['models'] is None:
            models_holder['models'] = load_models(ModelConfig())
        return organize_by_content(file_paths, input_path, output_path, models_holder['models'], silent)
    return MODE_HANDLERS[mode](file_paths, output_path)


def organize_directory(input_path, output_path, silent):
    """Run the interactive mode-selection / preview / confirm loop for one directory."""
    start_time = time.time()
    file_paths = collect_file_paths(input_path)
    logger.info("Loaded %d file paths in %.2f seconds", len(file_paths), time.time() - start_time)

    if not silent:
        print("Directory tree before organizing:")
        display_directory_tree(input_path)

    models_holder = {'models': None}
    while True:
        mode = cli.get_mode_selection()
        operations = plan_operations(mode, file_paths, input_path, output_path, models_holder, silent)

        logger.info("Proposed directory structure:")
        if not silent:
            print(os.path.abspath(output_path))
            cli.print_simulated_tree(cli.simulate_directory_tree(operations, output_path))

        if cli.get_yes_no("Would you like to proceed with these changes? (yes/no): "):
            os.makedirs(output_path, exist_ok=True)
            logger.info("Performing file operations...")
            execute_operations(operations, dry_run=False, silent=silent)
            logger.info("The files have been organized successfully.")
            return

        if not cli.get_yes_no("Would you like to choose another sorting method? (yes/no): "):
            logger.info("Operation canceled by the user.")
            return


def main():
    ensure_nltk_data()

    # Optional CLI args let a wrapper script (e.g. run.sh) supply the folder
    # to organize without an interactive prompt: `python main.py <input> [output]`
    cli_input_path = sys.argv[1] if len(sys.argv) > 1 else None
    cli_output_path = sys.argv[2] if len(sys.argv) > 2 else None

    print("-" * 50)
    print("**NOTE: Silent mode logs all outputs to a text file instead of displaying them in the terminal.")
    silent_mode = cli.get_yes_no("Would you like to enable silent mode? (yes/no): ")
    log_path = configure_logging(silent=silent_mode, log_dir=LOG_DIR)
    print(f"Logging this run to: {log_path}")

    while True:
        input_path = cli.prompt_input_path(cli_input_path)
        cli_input_path = None  # only reuse the CLI-supplied path for the first directory
        logger.info("Input path successfully uploaded: %s", input_path)

        output_path = cli.prompt_output_path(input_path, cli_output_path)
        cli_output_path = None  # only reuse the CLI-supplied path for the first directory
        logger.info("Output path successfully set to: %s", output_path)

        organize_directory(input_path, output_path, silent_mode)

        if not cli.get_yes_no("Would you like to organize another directory? (yes/no): "):
            break


if __name__ == '__main__':
    main()
