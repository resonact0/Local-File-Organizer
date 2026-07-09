"""Persistence of a run's category taxonomy (and item assignments) as a
manifest JSON in the output root. Later runs reuse the stored taxonomy so
bucket names stay stable, and the manifest file doubles as the marker that
protects an organized tree from being re-organized (see
file_utils.collect_file_paths)."""

import datetime
import json
import os

from logging_setup import get_logger

logger = get_logger(__name__)

MANIFEST_NAME = '.file_organizer_manifest.json'
MANIFEST_VERSION = 1


def load_manifest(output_path):
    """Load the manifest from `output_path`, or None if absent/unusable."""
    manifest_path = os.path.join(output_path, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Could not read manifest %s (%s); ignoring it", manifest_path, exc)
        return None
    if data.get('version') != MANIFEST_VERSION:
        logger.warning(
            "Manifest %s has unsupported version %r; ignoring it",
            manifest_path, data.get('version'),
        )
        return None
    logger.info(
        "Loaded manifest from %s (%d categories)",
        manifest_path, len(data.get('taxonomy', [])),
    )
    return data


def save_manifest(output_path, taxonomy, items):
    """Write the manifest to `output_path`, preserving the original 'created'
    timestamp when overwriting. Returns the manifest path."""
    manifest_path = os.path.join(output_path, MANIFEST_NAME)
    now = datetime.datetime.now().isoformat(timespec='seconds')

    existing = load_manifest(output_path)
    created = existing['created'] if existing else now
    previous_items = existing.get('items', []) if existing else []

    data = {
        'version': MANIFEST_VERSION,
        'created': created,
        'updated': now,
        'taxonomy': list(taxonomy),
        'items': previous_items + [
            {
                'source': item.source,
                'kind': item.kind,
                'cleaned_name': item.cleaned_name,
                'description': item.description,
                'category': item.category,
                'file_count': len(item.files),
            }
            for item in items
        ],
    }
    os.makedirs(output_path, exist_ok=True)
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Saved manifest to %s", manifest_path)
    return manifest_path
