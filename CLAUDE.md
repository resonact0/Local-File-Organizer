# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A privacy-first CLI that organizes a directory of files locally, using Ollama-served
models (no cloud calls). Three modes: **by content** (LLM-derived topic buckets),
**by date** (year/month from mtime), **by type** (extension). Only content mode
touches the models.

## Running

```bash
./run.sh <folder-to-organize> [output-folder]   # preferred: sets up venv, Ollama, models, resource caps
python main.py <input> [output]                  # direct; assumes venv active + Ollama running
```

`run.sh` is the real entrypoint and does a lot beyond launching Python: creates/activates
`venv`, `pip install`s requirements, ensures an Ollama server (native CLI → existing
Docker container → new Docker container), pulls the two required models, wraps the run in
a **systemd user scope with CPU/RAM cgroup caps** (a heavy run has frozen the desktop
before — see the comments), and runs `occ files:scan` afterward if the output lives under
a Nextcloud data dir. Tunables: `ORGANIZER_CPU_QUOTA`, `ORGANIZER_MEM_MAX`,
`ORGANIZER_MEM_HIGH`, `NEXTCLOUD_CONTAINER`, `NEXTCLOUD_DATA_ROOT`.

The app is **interactive**: it prompts for silent mode, input/output paths, sort mode,
proceed y/n, and copy-vs-move. CLI args only pre-fill the first input/output. There is no
test suite and no linter configured.

Required models (see `config.py:ModelConfig`): text `qwen2.5:7b-instruct`, vision
`llava:7b`, at `http://localhost:11434`.

## Content-mode pipeline (the core)

`main.organize_by_content` wires the phases; the phases themselves live in two files:

- **`items.py`** — decides *what a unit of organization is* and *where its files go*.
  An **Item** is either one **trusted top-level folder** (kept intact as a unit) or one
  **loose/untrusted file**. `build_items` produces cheap subject-matter `signals` per item
  (folder name + sample stems / file-name + text excerpt / file-name + vision description /
  file-name + epub metadata). `build_operations` maps categorized items to
  `output/<category>/...` — **it does not rename files** (despite what the README implies).
- **`taxonomy.py`** — all content-mode LLM prompting. Four phases:
  1. `describe_items` — one-line topic description per item.
  2. `induce_taxonomy` — **map-reduce over ALL descriptions** (candidate topics per
     30-item chunk → one consolidation pass), not a sample. Produces `[{name, definition}]`
     buckets. Category names are forced to subject matter: format/container words
     (`book`, `pdf`, `document`, `misc`, `other`…) are banned and stripped.
  3. `assign_categories` — batched assignment (20 items/batch) so the model sees siblings;
     failures get one retry batch, then `other`.
  4. `review_pass` — retry `other` items with a closest-match prompt, then merge
     near-empty categories into larger ones.

### Two invariants that shape the whole design

- **Stable taxonomy across runs (idempotency).** The output root carries a manifest
  (`manifest.py`, `.file_organizer_manifest.json`). On re-run, `induce_taxonomy` receives
  the previous taxonomy as `existing`, pins those buckets verbatim, and only asks the model
  what's *genuinely new* — so already-organized files keep a stable home and bucket names
  don't churn.
- **Never re-organize a previous output.** The manifest file doubles as a marker:
  `file_utils.collect_file_paths` skips any subtree containing it. This stops generated
  category folders from being fed back into classification when the output sits inside the input.

### Trust heuristic

`file_utils.split_by_folder_trust` + `is_junk_folder_name` decide which existing folders to
respect. A file is **trusted** (location kept, AI skipped) only if its *top-level* folder
under the input root is a meaningful, user-chosen name — only that top-level name is
checked, not every intermediate folder, so a folder like `coursera/` stays one intact item
even if something several levels down happens to be named `files` or `old`. Junk top-level
names (`Downloads`, `IMG_1234`, `New Folder (2)`, date-stamped/numeric dirs, etc.) and files
sitting directly in the input root are **untrusted** → they go through the content pipeline.

## Cross-cutting conventions

- **Logging, not print.** `logging_setup.configure_logging()` is called once at startup;
  every module uses `logger = get_logger(__name__)`. Each run gets a timestamped
  `logs/run_*.log` at full DEBUG; non-silent mode also streams INFO+ to the terminal.
  User-facing terminal UI (prompts, trees, `rich` progress bars) is the exception and stays
  in `cli.py` / the progress blocks.
- **Determinism.** Text inference runs at `temperature=0` (`ollama_inference.py`) so identical
  inputs organize identically.
- **Ollama adapter shim.** `ollama_inference.py` mimics the old Nexa SDK call shapes
  (`create_completion` → `{'choices':[{'text':...}]}`, `_chat` → a streaming generator) that
  the rest of the code relies on; keep those shapes if you touch it.
- **Name cleaning is pure regex** (`name_cleaning.py`) — strips torrent/release-group/format
  junk from titles; no model involved. `sanitize_path_component` makes any string a safe
  single path component.
- **File readers** (`file_utils.py`, `_READERS_BY_EXTENSION`) are best-effort: they truncate
  (PDF first 3 pages, text first 3000 chars) and return `None` on failure. Adding a readable
  format means updating both the reader map and `config.TEXT_EXTENSIONS`; a type-mode-only
  format goes in `config.TEXT_TYPE_SUBFOLDERS`.

## Nextcloud note

Files may live under a Dockerized Nextcloud data dir. Direct on-disk copies/moves stay
invisible in the Nextcloud UI until `occ files:scan` re-indexes them; `run.sh` does this
automatically for organized paths under `NEXTCLOUD_DATA_ROOT`. Manual edits there also need
`www-data` ownership.
