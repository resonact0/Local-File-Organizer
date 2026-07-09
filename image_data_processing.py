"""Generate folder/file names for image files by describing them with a
vision-language model, then naming them with a text model."""

from ai_metadata import generate_filename, generate_hierarchical_foldername, process_single_file

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


def generate_image_metadata(image_path, image_inference, text_inference, progress, task_id):
    """Generate (foldername, filename, description) for a single image."""
    description = _describe_image(image_path, image_inference)
    progress.update(task_id, advance=1 / 3)

    filename = generate_filename(
        text_inference,
        FILENAME_PROMPT_TEMPLATE.format(description=description),
        description,
        IMAGE_UNWANTED_WORDS,
        fallback_prefix='image',
        source_path=image_path,
    )
    progress.update(task_id, advance=1 / 3)

    foldername = generate_hierarchical_foldername(
        text_inference,
        FOLDERNAME_PROMPT_TEMPLATE.format(description=description),
        description,
        IMAGE_UNWANTED_WORDS,
        fallback='images',
    )
    progress.update(task_id, advance=1 / 3)

    return foldername, filename, description


def process_single_image(image_path, image_inference, text_inference, silent=False):
    return process_single_file(
        image_path,
        lambda progress, task_id: generate_image_metadata(
            image_path, image_inference, text_inference, progress, task_id
        ),
        silent=silent,
    )


def process_image_files(image_paths, image_inference, text_inference, silent=False):
    """Process image files sequentially, returning a list of FileMetadata."""
    return [process_single_image(p, image_inference, text_inference, silent=silent) for p in image_paths]
