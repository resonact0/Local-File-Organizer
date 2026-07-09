"""Generate folder/file names for image files by describing them with a
vision-language model, then naming them with a text model.

Description and naming are separate passes (describe_image_files then
name_image_files) so the caller can induce a content-derived category
taxonomy from all descriptions -- image and text alike -- before any
foldername is decided."""

import time

from rich.progress import BarColumn, Progress, TextColumn, TimeElapsedColumn

from ai_metadata import FileMetadata, generate_filename, generate_hierarchical_foldername
from logging_setup import get_logger

logger = get_logger(__name__)

IMAGE_UNWANTED_WORDS = {
    'image', 'picture', 'photo', 'jpg', 'png', 'jpeg', 'gif', 'bmp', 'svg', 'logo',
    'red', 'blue', 'green', 'color', 'colors', 'colored', 'graphic', 'graphics',
}

DESCRIPTION_PROMPT = (
    "Please provide a detailed description of this image, focusing on the main "
    "subject and any important details."
)

FILENAME_PROMPT_TEMPLATE = """Based on the description below, generate a specific and descriptive filename for the image.
Limit the filename to a maximum of 3 words. Use nouns and avoid starting with verbs like 'depicts', 'shows', 'presents', etc.
Do not include any data type words like 'image', 'jpg', 'png', etc. Use only letters and connect words with underscores.

Description: {description}

Example:
Description: A photo of a sunset over the mountains.
Filename: sunset_over_mountains

Now generate the filename.

Output only the filename, without any additional text.

Filename:"""

FOLDERNAME_PROMPT_TEMPLATE = """Based on the description below, generate a general category or theme that best represents the main subject of this image.
This will be used as the folder name. Limit the category to a maximum of 2 words. Use nouns and avoid verbs.
Do not include specific details, words from the filename, or any generic terms like 'untitled' or 'unknown'.

Description: {description}

Examples:
1. Description: A photo of a sunset over the mountains.
   Category: landscapes

2. Description: An image of a smartphone displaying a storage app with various icons and information.
   Category: technology

3. Description: A close-up of a blooming red rose with dew drops.
   Category: nature

Now generate the category.

Output only the category, without any additional text.

Category:"""


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


def name_image_file(image_path, description, text_inference, categories):
    """Generate (foldername, filename) for an already-described image."""
    filename = generate_filename(
        text_inference,
        FILENAME_PROMPT_TEMPLATE.format(description=description),
        description,
        IMAGE_UNWANTED_WORDS,
        fallback_prefix='image',
        source_path=image_path,
    )
    foldername = generate_hierarchical_foldername(
        text_inference,
        FOLDERNAME_PROMPT_TEMPLATE.format(description=description),
        description,
        IMAGE_UNWANTED_WORDS,
        fallback='images',
        categories=categories,
    )
    return FileMetadata(file_path=image_path, foldername=foldername, filename=filename, description=description)


def name_image_files(image_descriptions, text_inference, categories, silent=False):
    """Name each described image, returning a list of FileMetadata."""
    metadata = []
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TimeElapsedColumn(),
        disable=silent,
    ) as progress:
        task_id = progress.add_task("Naming images", total=len(image_descriptions) or 1)
        for image_path, description in image_descriptions:
            file_metadata = name_image_file(image_path, description, text_inference, categories)
            logger.info("Named '%s' -> %s/%s", image_path, file_metadata.foldername, file_metadata.filename)
            metadata.append(file_metadata)
            progress.update(task_id, advance=1)
    return metadata
