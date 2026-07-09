"""Entry point: interactively (or via CLI args) organize a directory of files
by content, date, or type, using local Ollama models for content understanding."""

import os
import sys
import time

import cli
from config import LOG_DIR, ModelConfig
from data_processing_common import (
    execute_operations,
    process_files_by_date,
    process_files_by_type,
    remove_empty_dirs,
)
from file_utils import collect_file_paths, display_directory_tree
from items import build_items, build_operations
from logging_setup import configure_logging, get_logger
from manifest import load_manifest, save_manifest
from models import load_models
from taxonomy import assign_categories, describe_items, induce_taxonomy, review_pass

logger = get_logger(__name__)

# Above this many proposed files, printing the full tree just floods the
# terminal before the user can read it -- show a per-category summary and
# write the full tree to a file instead.
TREE_INLINE_LIMIT = 30


def organize_by_content(file_paths, input_path, output_path, models, silent):
    """Plan operations for 'by content' mode.

    Pipeline: group files into items (one per trusted top-level folder, one
    per loose file) -> describe each item's subject matter -> induce a
    topic-based bucket taxonomy from ALL descriptions (reusing the taxonomy
    stored in the output's manifest, if any, so buckets stay stable across
    runs) -> assign every item to a bucket in batches -> review stragglers.

    Returns (operations, items, taxonomy) so the caller can persist the
    manifest after executing.
    """
    items = build_items(file_paths, input_path, models.image_inference, silent=silent)
    describe_items(models.text_inference, items, silent=silent)

    manifest_data = load_manifest(output_path)
    existing = manifest_data['taxonomy'] if manifest_data else ()
    taxonomy = induce_taxonomy(
        models.text_inference,
        [item.description for item in items],
        existing=existing,
    )
    logger.info("Using top-level buckets: %s", ', '.join(cat['name'] for cat in taxonomy))

    assign_categories(models.text_inference, items, taxonomy, silent=silent)
    taxonomy = review_pass(models.text_inference, items, taxonomy)

    return build_operations(items, output_path, input_path), items, taxonomy


MODE_HANDLERS = {
    'date': process_files_by_date,
    'type': process_files_by_type,
}


def plan_operations(mode, file_paths, input_path, output_path, models_holder, silent):
    """Compute (operations, items, taxonomy) for the selected mode, lazily
    loading models for 'content' mode. Items/taxonomy are None for the
    non-content modes, which need no manifest."""
    if mode == 'content':
        if models_holder['models'] is None:
            models_holder['models'] = load_models(ModelConfig())
        return organize_by_content(file_paths, input_path, output_path, models_holder['models'], silent)
    return MODE_HANDLERS[mode](file_paths, output_path), None, None


def organize_directory(input_path, output_path, silent):
    """Run the interactive mode-selection / preview / confirm loop for one directory."""
    abs_input = os.path.abspath(input_path)
    abs_output = os.path.abspath(output_path)
    if os.path.commonpath([abs_output, abs_input]) == abs_input:
        logger.warning(
            "Output directory is inside the input directory; the manifest "
            "marker will protect it from being re-organized by later runs."
        )

    start_time = time.time()
    file_paths = collect_file_paths(input_path)
    logger.info("Loaded %d file paths in %.2f seconds", len(file_paths), time.time() - start_time)

    if not silent:
        print("Directory tree before organizing:")
        display_directory_tree(input_path)

    models_holder = {'models': None}
    while True:
        mode = cli.get_mode_selection()
        operations, items, taxonomy = plan_operations(
            mode, file_paths, input_path, output_path, models_holder, silent
        )

        logger.info("Proposed directory structure:")
        if not silent:
            print(os.path.abspath(output_path))
            tree = cli.simulate_directory_tree(operations, output_path)
            if len(operations) > TREE_INLINE_LIMIT:
                cli.print_category_summary(tree)
                preview_path = cli.write_simulated_tree(tree, output_path, LOG_DIR)
                print(f"Full proposed structure written to: {preview_path}")
            else:
                cli.print_simulated_tree(tree)

        if cli.get_yes_no("Would you like to proceed with these changes? (yes/no): "):
            move = cli.get_transfer_mode() == 'move'
            os.makedirs(output_path, exist_ok=True)
            logger.info("Performing file operations...")
            execute_operations(operations, dry_run=False, silent=silent, move=move)
            if items is not None:
                save_manifest(output_path, taxonomy, items)
            if move:
                remove_empty_dirs(input_path)
            logger.info("The files have been organized successfully.")
            return

        if not cli.get_yes_no("Would you like to choose another sorting method? (yes/no): "):
            logger.info("Operation canceled by the user.")
            return


def main():
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
