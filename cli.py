"""Interactive command-line prompts and directory-tree display helpers."""

import datetime
import os


def get_yes_no(prompt):
    """Prompt the user for a yes/no response; '/exit' quits the program."""
    while True:
        response = input(prompt).strip().lower()
        if response in ('yes', 'y'):
            return True
        if response in ('no', 'n'):
            return False
        if response == '/exit':
            print("Exiting program.")
            raise SystemExit(0)
        print("Please enter 'yes' or 'no'. To exit, type '/exit'.")


def get_transfer_mode():
    """Ask whether to copy or move the files; empty input defaults to copy."""
    while True:
        response = input("Copy files or move them? (copy/move) [copy]: ").strip().lower()
        if response in ('', 'copy', 'c'):
            return 'copy'
        if response in ('move', 'm'):
            return 'move'
        if response == '/exit':
            print("Exiting program.")
            raise SystemExit(0)
        print("Please enter 'copy' or 'move'. To exit, type '/exit'.")


def get_mode_selection():
    """Prompt the user to choose an organizing mode: content, date, or type."""
    modes = {'1': 'content', '2': 'date', '3': 'type'}
    while True:
        print("Please choose the mode to organize your files:")
        print("1. By Content")
        print("2. By Date")
        print("3. By Type")
        response = input("Enter 1, 2, or 3 (or type '/exit' to exit): ").strip()
        if response == '/exit':
            print("Exiting program.")
            raise SystemExit(0)
        if response in modes:
            return modes[response]
        print("Invalid selection. Please enter 1, 2, or 3. To exit, type '/exit'.")


def prompt_input_path(cli_arg=None):
    """Resolve the input directory: from a CLI arg if valid, otherwise by prompting."""
    if cli_arg and os.path.exists(cli_arg):
        return cli_arg
    if cli_arg:
        print(f"Input path {cli_arg} does not exist. Please enter a valid path.")

    path = input("Enter the path of the directory you want to organize: ").strip()
    while not os.path.exists(path):
        print(f"Input path {path} does not exist. Please enter a valid path.")
        path = input("Enter the path of the directory you want to organize: ").strip()
    return path


def prompt_output_path(input_path, cli_arg=None):
    """Resolve the output directory: from a CLI arg, user input, or a default sibling folder."""
    if cli_arg:
        return cli_arg
    output_path = input(
        "Enter the path to store organized files and folders "
        "(press Enter to use 'organized_folder' in the input directory): "
    ).strip()
    return output_path or os.path.join(os.path.dirname(input_path), 'organized_folder')


def simulate_directory_tree(operations, base_path):
    """Build a nested-dict tree of the directory structure the operations would produce."""
    tree = {}
    for op in operations:
        rel_path = os.path.relpath(op['destination'], base_path)
        current_level = tree
        for part in rel_path.split(os.sep):
            current_level = current_level.setdefault(part, {})
    return tree


def _tree_lines(tree, prefix=''):
    """Yield lines of a `tree`-command-style rendering of a nested-dict tree."""
    pointers = ['├── '] * (len(tree) - 1) + ['└── '] if tree else []
    for pointer, key in zip(pointers, tree):
        yield prefix + pointer + key
        if tree[key]:
            extension = '│   ' if pointer == '├── ' else '    '
            yield from _tree_lines(tree[key], prefix + extension)


def print_simulated_tree(tree, prefix=''):
    """Print a nested-dict directory tree in `tree`-command style."""
    for line in _tree_lines(tree, prefix):
        print(line)


def count_files(tree):
    """Count the file leaves in a simulated directory tree."""
    if not tree:
        return 1
    return sum(count_files(subtree) for subtree in tree.values())


def print_category_summary(tree):
    """Print one line per top-level entry with its file count, so a large
    proposed structure can be scanned without paging through every file."""
    for key in sorted(tree, key=lambda k: -count_files(tree[k])):
        print(f"  {key}: {count_files(tree[key])} file(s)")
    print(f"  Total: {count_files(tree)} file(s)")


def write_simulated_tree(tree, base_path, log_dir):
    """Write the full proposed directory tree to a timestamped text file
    under `log_dir`, for review when it's too large to scan in the terminal.
    Returns the file path."""
    os.makedirs(log_dir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = os.path.join(log_dir, f"structure_preview_{stamp}.txt")
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(log_dir, f"structure_preview_{stamp}_{counter}.txt")
        counter += 1

    with open(file_path, 'w') as f:
        f.write(os.path.abspath(base_path) + '\n')
        for line in _tree_lines(tree):
            f.write(line + '\n')
    return file_path
