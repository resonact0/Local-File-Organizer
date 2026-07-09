"""Generate folder/file names for text-based files by summarizing them with
a text model, then naming them from that summary."""

from ai_metadata import generate_filename, generate_hierarchical_foldername, process_single_file

TEXT_UNWANTED_WORDS = {
    'document', 'key', 'information', 'note', 'notes', 'ideas', 'concepts',
    'i', 'we', 'you', 'they', 'he', 'she', 'it', 'that', 'which', 'are', 'were', 'was', 'be',
    'have', 'has', 'had', 'do', 'does', 'did', 'but', 'if', 'or', 'because', 'about', 'into',
    'through', 'during', 'before', 'after', 'above', 'any', 'each', 'few', 'more', 'most',
    'other', 'some', 'such', 'no', 'nor', 'not', 'own', 'same', 'so', 'than', 'too', 'very',
    's', 't', 'can', 'will', 'just', 'don', 'should', 'now', 'new', 'discusses',
}

SUMMARY_PROMPT_TEMPLATE = """Provide a concise and accurate summary of the following text, focusing on the main ideas and key details.
Limit your summary to a maximum of 150 words.

Text: {text}

Summary:"""

FILENAME_PROMPT_TEMPLATE = """Based on the summary below, generate a specific and descriptive filename that captures the essence of the document.
Limit the filename to a maximum of 3 words. Use nouns and avoid starting with verbs like 'depicts', 'shows', 'presents', etc.
Do not include any data type words like 'text', 'document', 'pdf', etc. Use only letters and connect words with underscores.

Summary: {description}

Examples:
1. Summary: A research paper on the fundamentals of string theory.
   Filename: fundamentals_of_string_theory

2. Summary: An article discussing the effects of climate change on polar bears.
   Filename: climate_change_polar_bears

Now generate the filename.

Output only the filename, without any additional text.

Filename:"""

FOLDERNAME_PROMPT_TEMPLATE = """Based on the summary below, generate a general category or theme that best represents the main subject of this document.
This will be used as the folder name. Limit the category to a maximum of 2 words. Use nouns and avoid verbs.
Do not include specific details, words from the filename, or any generic terms like 'untitled' or 'unknown'.

Summary: {description}

Examples:
1. Summary: A research paper on the fundamentals of string theory.
   Category: physics

2. Summary: An article discussing the effects of climate change on polar bears.
   Category: environment

Now generate the category.

Output only the category, without any additional text.

Category:"""


def _summarize(text, text_inference):
    prompt = SUMMARY_PROMPT_TEMPLATE.format(text=text)
    response = text_inference.create_completion(prompt)
    return response['choices'][0]['text'].strip()


def generate_text_metadata(input_text, file_path, text_inference, progress, task_id):
    """Generate (foldername, filename, description) for a single text document."""
    description = _summarize(input_text, text_inference)
    progress.update(task_id, advance=1 / 3)

    filename = generate_filename(
        text_inference,
        FILENAME_PROMPT_TEMPLATE.format(description=description),
        description,
        TEXT_UNWANTED_WORDS,
        fallback_prefix='document',
        source_path=file_path,
    )
    progress.update(task_id, advance=1 / 3)

    foldername = generate_hierarchical_foldername(
        text_inference,
        FOLDERNAME_PROMPT_TEMPLATE.format(description=description),
        description,
        TEXT_UNWANTED_WORDS,
        fallback='documents',
    )
    progress.update(task_id, advance=1 / 3)

    return foldername, filename, description


def process_single_text_file(file_path, text, text_inference, silent=False):
    return process_single_file(
        file_path,
        lambda progress, task_id: generate_text_metadata(text, file_path, text_inference, progress, task_id),
        silent=silent,
    )


def process_text_files(text_tuples, text_inference, silent=False):
    """Process (file_path, text) tuples sequentially, returning a list of FileMetadata."""
    return [process_single_text_file(fp, text, text_inference, silent=silent) for fp, text in text_tuples]
