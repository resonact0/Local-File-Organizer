"""Content-derived category taxonomy: describe items, induce a stable set of
topic-based top-level buckets from ALL descriptions (map-reduce, not a sample),
assign every item to a bucket in batches, then review the stragglers.

All content-mode LLM prompting lives here; items.py decides what an "item" is
and where its files go, main.py just wires the phases together."""

import re
from collections import Counter

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn, TimeRemainingColumn

from config import CATEGORY_TAXONOMY
from data_processing_common import sanitize_filename
from logging_setup import get_logger

logger = get_logger(__name__)

# Format/container words say how content is packaged, never what it is about,
# so they are banned as category names and stripped from candidate labels
# (a books directory would otherwise induce buckets like "books"/"ebook").
_FORBIDDEN_CATEGORY_WORDS = frozenset({
    'book', 'books', 'ebook', 'ebooks', 'pdf', 'pdfs', 'magazine', 'magazines',
    'document', 'documents', 'collection', 'collections', 'file', 'files',
    'folder', 'folders', 'misc', 'miscellaneous', 'other', 'others',
})

OTHER_CATEGORY = {'name': 'other', 'definition': 'anything that does not fit the categories above'}


ITEM_DESCRIPTION_PROMPT_TEMPLATE = """You are cataloguing a personal file collection.

Item information:
{signals}

Write exactly one line (under 20 words) describing what this item is ABOUT.
Focus on subject matter and topic, never on file format or packaging.
Do not use the words file, folder, pdf, epub, ebook, document, or collection.
If it is a book with a clear title and author, use the form: <title> by <author> - <topic>.

Description:"""


CHUNK_TOPIC_PROMPT_TEMPLATE = """Here are one-line descriptions of items in a personal file collection:

{descriptions}

List the main subject-matter topics these items cover.
Rules:
- Between 3 and 10 topics.
- lowercase snake_case, one to three words each (e.g. web_development, music, personal_finance).
- Topics must describe subject matter. NEVER use file formats or container words
  such as: book, books, ebook, pdf, magazine, document, collection, files, misc, other.
- Never list two topics that mean nearly the same thing.

Output only the topics, one per line, nothing else.

Topics:"""


CONSOLIDATION_PROMPT_TEMPLATE = """Candidate topic labels were extracted from a large personal file collection.
Each label is followed by how many times it was proposed:

{candidates}

Consolidate these into a final set of {min_categories} to {max_categories} top-level
folder categories that together cover the whole collection.
Rules:
- Merge synonyms and near-duplicates into one category (e.g. programming, coding and
  software_development must become a single category).
- Category names are lowercase snake_case, one to three words.
- NEVER use file formats or container words as categories: book, books, ebook, pdf,
  magazine, document, collection, files, misc, other.
- Prefer labels that were proposed more often.
- Give each category a one-line definition of what belongs in it.

Output one category per line, and nothing else, in the format:
<category_name>: <one-line definition>

Categories:"""

# When a previous run's taxonomy exists, it is kept verbatim (stable buckets
# across runs) and the model is only asked what is genuinely missing from it.
EXTENSION_PROMPT_TEMPLATE = """An organized file collection already uses these top-level categories:

{existing_lines}

New items arrived, and these candidate topic labels were extracted from them
(each followed by how many times it was proposed):

{candidates}

Most candidates should fit one of the existing categories. Identify only the
topics that clearly do NOT fit any existing category and deserve a new
top-level folder.
Rules:
- Category names are lowercase snake_case, one to three words.
- NEVER use file formats or container words as categories: book, books, ebook, pdf,
  magazine, document, collection, files, misc, other.
- If every candidate fits an existing category, output exactly: none

Output one line per NEW category only, in the format:
<category_name>: <one-line definition>

New categories:"""


ASSIGNMENT_PROMPT_TEMPLATE = """Assign each numbered item to exactly one category from this list.

Categories:
{taxonomy_block}

Examples of good assignments (from a different collection):
- "Guitar chord techniques for beginner players" -> music
- "Python web scraping walkthrough by Ryan Mitchell" -> programming
- "Monthly household budget spreadsheet" -> personal_finance

Items:
{items_block}

Rules:
- Use only category names from the list above, spelled exactly as shown.
- Pick the closest match by subject matter.
- Answer "other" only when nothing on the list is even loosely related.

Output one line per item in the format "number: category", and nothing else.

Assignments:"""


OTHER_RETRY_PROMPT_TEMPLATE = """These items were placed in the catch-all "other" category on a first pass.
Double-check each one: if one of the categories below genuinely covers its
subject matter, assign it there. If none truly fits, answer "other" again --
a wrong category is worse than "other".

Categories:
{taxonomy_block}

Items:
{items_block}

Output one line per item in the format "number: category", and nothing else.

Assignments:"""


MERGE_SMALL_PROMPT_TEMPLATE = """In an organized file collection, these categories ended up with very few items:

{small_block}

The larger categories available are:
{taxonomy_block}

For each small category, either merge it into the closest larger category, or answer
"keep" if it is genuinely distinct and nothing else fits.

Output one line per small category in the format "small_name: target_name" or
"small_name: keep", and nothing else."""


def _complete(text_inference, prompt, max_tokens=None):
    response = text_inference.create_completion(prompt, max_tokens=max_tokens)
    return response['choices'][0]['text'].strip()


def _normalize_label(raw):
    """Turn a model-proposed label into a snake_case category name with
    forbidden format words stripped; '' if nothing meaningful remains."""
    name = sanitize_filename(raw, max_words=3)
    words = [w for w in name.split('_') if w and w not in _FORBIDDEN_CATEGORY_WORDS]
    return '_'.join(words)


def _taxonomy_block(taxonomy):
    return '\n'.join(f"- {cat['name']}: {cat['definition']}" for cat in taxonomy)


def _parse_name_def_lines(raw):
    """Parse 'name: definition' lines into [{'name', 'definition'}, ...]."""
    categories = []
    seen = set()
    for line in raw.splitlines():
        line = re.sub(r'^\s*[-*\d.]+\s*', '', line.strip())
        # Models sometimes echo the format spec literally, producing lines
        # like "name: music: songs and instruments" -- drop the label prefix.
        label_match = re.match(r'^(?:<?\s*(?:category[_ ]?)?name\s*>?)\s*:\s*(.+)$', line, re.IGNORECASE)
        if label_match and ':' in label_match.group(1):
            line = label_match.group(1)
        if ':' not in line:
            continue
        name_part, definition = line.split(':', 1)
        name = _normalize_label(name_part.strip(' <>'))
        definition = definition.strip()
        # Reject echoes of the prompt's format spec and sanitize_filename's
        # 'untitled' empty-input sentinel -- neither is a real category.
        if (not name or name in ('untitled', 'category_name')
                or definition.startswith('<') or not definition):
            continue
        if name not in seen:
            seen.add(name)
            categories.append({'name': name, 'definition': definition})
    return categories


def _parse_assignments(raw, expected_numbers, valid_names):
    """Parse 'number: category' lines into {number: category}, keeping only
    expected numbers whose category is in `valid_names`. Tolerates the model
    echoing item text after the category name."""
    assignments = {}
    for line in raw.splitlines():
        match = re.match(r'\s*(\d+)\s*[:.\-)]\s*([A-Za-z][A-Za-z0-9_ ]*)', line)
        if not match:
            continue
        number = int(match.group(1))
        if number not in expected_numbers:
            continue
        words = match.group(2).lower().strip().split()
        # Longest prefix of the answer that is a valid category, so
        # "3: music - guitar book" resolves to "music" and
        # "5: personal finance" resolves to "personal_finance".
        for end in range(len(words), 0, -1):
            candidate = '_'.join(words[:end])
            if candidate in valid_names:
                assignments[number] = candidate
                break
    return assignments


def describe_items(text_inference, items, silent=False):
    """Fill item.description with a one-line topic description of each item."""
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        disable=silent,
    ) as progress:
        task_id = progress.add_task("Describing items", total=len(items) or 1)
        for item in items:
            prompt = ITEM_DESCRIPTION_PROMPT_TEMPLATE.format(signals=item.signals)
            raw = _complete(text_inference, prompt, max_tokens=60)
            item.description = ' '.join(raw.splitlines()).strip() or item.cleaned_name
            logger.debug("Described '%s': %s", item.source, item.description)
            progress.update(task_id, advance=1)


def _extract_candidate_topics(text_inference, chunk):
    prompt = CHUNK_TOPIC_PROMPT_TEMPLATE.format(
        descriptions='\n'.join(f"- {d}" for d in chunk),
    )
    raw = _complete(text_inference, prompt, max_tokens=120)
    labels = []
    for line in raw.splitlines():
        label = _normalize_label(re.sub(r'^\s*[-*\d.]+\s*', '', line))
        if label:
            labels.append(label)
    return labels


def _consolidate(text_inference, candidate_counts, min_categories, max_categories):
    prompt = CONSOLIDATION_PROMPT_TEMPLATE.format(
        candidates='\n'.join(f"{label} ({count})" for label, count in candidate_counts),
        min_categories=min_categories,
        max_categories=max_categories,
    )
    return _parse_name_def_lines(_complete(text_inference, prompt, max_tokens=500))


def _extend(text_inference, candidate_counts, existing):
    prompt = EXTENSION_PROMPT_TEMPLATE.format(
        existing_lines='\n'.join(
            f"- {cat['name']}: {cat['definition']}"
            for cat in existing if cat['name'] != 'other'
        ),
        candidates='\n'.join(f"{label} ({count})" for label, count in candidate_counts),
    )
    raw = _complete(text_inference, prompt, max_tokens=300)
    if raw.strip().lower().startswith('none'):
        return []
    existing_names = {cat['name'] for cat in existing}
    return [cat for cat in _parse_name_def_lines(raw) if cat['name'] not in existing_names]


def _fallback_taxonomy():
    return [
        {'name': name, 'definition': f"files about {name}"}
        for name in CATEGORY_TAXONOMY if name != 'other'
    ] + [OTHER_CATEGORY]


def induce_taxonomy(text_inference, descriptions, existing=(),
                    min_categories=5, max_categories=12, chunk_size=30):
    """Derive [{'name', 'definition'}, ...] top-level buckets from every item
    description (map: candidate topics per chunk; reduce: one consolidation
    pass over tallied candidates). Categories in `existing` (from a previous
    run's manifest) are pinned so bucket names stay stable across runs."""
    descriptions = [d for d in descriptions if d and d.strip()]
    existing = list(existing)
    if not descriptions:
        return existing if existing else _fallback_taxonomy()

    counts = Counter()
    for start in range(0, len(descriptions), chunk_size):
        chunk = descriptions[start:start + chunk_size]
        counts.update(_extract_candidate_topics(text_inference, chunk))
    top_candidates = counts.most_common(40)
    logger.info("Candidate topics (top 10): %s",
                ', '.join(f"{label}({count})" for label, count in top_candidates[:10]))

    if existing:
        # Previous runs' buckets are kept verbatim so already-organized files
        # keep a stable home; the model is only asked what's genuinely new.
        existing_names = {cat['name'] for cat in existing}
        if all(label in existing_names for label, _ in top_candidates[:10]):
            logger.info("All leading candidate topics already covered by the existing taxonomy; reusing it")
            return existing
        additions = _extend(text_inference, top_candidates, existing)[:5]
        if additions:
            logger.info("Extending taxonomy with new categories: %s",
                        ', '.join(cat['name'] for cat in additions))
        kept = [cat for cat in existing if cat['name'] != 'other']
        return kept + additions + [OTHER_CATEGORY]

    consolidated = _consolidate(text_inference, top_candidates, min_categories, max_categories)
    consolidated = [cat for cat in consolidated if cat['name'] != 'other'][:max_categories]
    if len(consolidated) < 2:
        logger.warning("Could not induce a usable taxonomy from content; falling back to defaults")
        return _fallback_taxonomy()
    consolidated.append(OTHER_CATEGORY)
    return consolidated


def _assign_batch(text_inference, numbered_items, taxonomy, prompt_template):
    """One assignment call for [(number, item), ...]; returns {number: category}."""
    prompt = prompt_template.format(
        taxonomy_block=_taxonomy_block(taxonomy),
        items_block='\n'.join(f"{number}. {item.description}" for number, item in numbered_items),
    )
    raw = _complete(text_inference, prompt, max_tokens=400)
    return _parse_assignments(
        raw,
        expected_numbers={number for number, _ in numbered_items},
        valid_names={cat['name'] for cat in taxonomy},
    )


def assign_categories(text_inference, items, taxonomy, batch_size=20, silent=False):
    """Assign every item a category from `taxonomy`, in batches so the model
    sees sibling items (more consistent than one call per item). Items the
    model fails to answer for get one retry batch, then 'other'."""
    numbered = list(enumerate(items, start=1))
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        disable=silent,
    ) as progress:
        task_id = progress.add_task("Categorizing items", total=len(numbered) or 1)
        failed = []
        for start in range(0, len(numbered), batch_size):
            batch = numbered[start:start + batch_size]
            assignments = _assign_batch(text_inference, batch, taxonomy, ASSIGNMENT_PROMPT_TEMPLATE)
            for number, item in batch:
                if number in assignments:
                    item.category = assignments[number]
                else:
                    failed.append((number, item))
            progress.update(task_id, advance=len(batch))

    for start in range(0, len(failed), batch_size):
        batch = failed[start:start + batch_size]
        assignments = _assign_batch(text_inference, batch, taxonomy, ASSIGNMENT_PROMPT_TEMPLATE)
        for number, item in batch:
            item.category = assignments.get(number, 'other')
            if number not in assignments:
                logger.warning("Could not categorize '%s'; filing under 'other'", item.source)

    for _, item in numbered:
        logger.info("Categorized '%s' -> %s", item.source, item.category)


def review_pass(text_inference, items, taxonomy, min_category_size=3, batch_size=20):
    """Second look at the weak spots: re-attempt 'other' items with a
    closest-match prompt, then merge near-empty categories into larger ones.
    Returns the (possibly reduced) taxonomy."""
    numbered = list(enumerate(items, start=1))

    other_items = [(number, item) for number, item in numbered if item.category == 'other']
    for start in range(0, len(other_items), batch_size):
        batch = other_items[start:start + batch_size]
        assignments = _assign_batch(text_inference, batch, taxonomy, OTHER_RETRY_PROMPT_TEMPLATE)
        for number, item in batch:
            if assignments.get(number, 'other') != 'other':
                logger.info("Review pass: '%s' 'other' -> '%s'", item.source, assignments[number])
                item.category = assignments[number]

    counts = Counter(item.category for item in items)
    small = [cat for cat in taxonomy
             if cat['name'] != 'other' and 0 < counts[cat['name']] < min_category_size]
    large = [cat for cat in taxonomy
             if cat['name'] != 'other' and counts[cat['name']] >= min_category_size]
    if not small or not large:
        return taxonomy

    by_category = {}
    for item in items:
        by_category.setdefault(item.category, []).append(item)
    small_block = '\n'.join(
        f"- {cat['name']} ({counts[cat['name']]} items): e.g. {by_category[cat['name']][0].description}"
        for cat in small
    )
    prompt = MERGE_SMALL_PROMPT_TEMPLATE.format(
        small_block=small_block,
        taxonomy_block=_taxonomy_block(large),
    )
    raw = _complete(text_inference, prompt, max_tokens=200)

    small_names = {cat['name'] for cat in small}
    large_names = {cat['name'] for cat in large}
    merged = {}
    for line in raw.splitlines():
        if ':' not in line:
            continue
        source, target = (part.strip().lower().replace(' ', '_') for part in line.split(':', 1))
        source = re.sub(r'^[-*\s]+', '', source)
        if source in small_names and target in large_names:
            merged[source] = target

    for item in items:
        if item.category in merged:
            item.category = merged[item.category]
    for source, target in merged.items():
        logger.info("Merged small category '%s' into '%s'", source, target)
    return [cat for cat in taxonomy if cat['name'] not in merged]
