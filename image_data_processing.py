"""Describe image files with a vision-language model. The descriptions feed
the shared item pipeline (items.py / taxonomy.py), which handles taxonomy
induction and category assignment for images and text alike."""

import time

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from logging_setup import get_logger

logger = get_logger(__name__)

DESCRIPTION_PROMPT = (
    "Please provide a detailed description of this image, focusing on the main "
    "subject and any important details."
)


def _get_text_from_generator(generator):
    """Drain a streaming chat generator into a single string."""
    response_text = ""
    for response in generator:
        for choice in response.get('choices', []):
            delta = choice.get('delta', {})
            if 'content' in delta:
                response_text += delta['content']
    return response_text


def _describe_image(image_path, image_inference):
    generator = image_inference._chat(DESCRIPTION_PROMPT, image_path)
    return _get_text_from_generator(generator).strip()


def describe_image_files(image_paths, image_inference, silent=False):
    """Describe each image with the vision model, returning [(path, description), ...]."""
    results = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        disable=silent,
    ) as progress:
        task_id = progress.add_task("Describing images", total=len(image_paths) or 1)
        for image_path in image_paths:
            start_time = time.time()
            description = _describe_image(image_path, image_inference)
            logger.info("Described '%s' in %.2fs", image_path, time.time() - start_time)
            logger.debug("Description for '%s': %s", image_path, description)
            results.append((image_path, description))
            progress.update(task_id, advance=1)
    return results
