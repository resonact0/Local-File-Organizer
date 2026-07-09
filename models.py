"""Loads and holds the local Ollama models used for content understanding."""

from dataclasses import dataclass

from config import ModelConfig
from logging_setup import get_logger
from ollama_inference import OllamaTextInference, OllamaVLMInference
from output_filter import filter_specific_output

logger = get_logger(__name__)


@dataclass
class ModelBundle:
    """Holds the initialized vision and text inference clients."""
    image_inference: OllamaVLMInference
    text_inference: OllamaTextInference


def load_models(config: ModelConfig = ModelConfig()) -> ModelBundle:
    """Initialize the vision and text models served by Ollama."""
    logger.info("Loading models (vision=%s, text=%s)...", config.vision_model, config.text_model)
    with filter_specific_output():
        bundle = ModelBundle(
            image_inference=OllamaVLMInference(model=config.vision_model, host=config.host),
            text_inference=OllamaTextInference(model=config.text_model, host=config.host),
        )
    logger.info("Models loaded successfully.")
    return bundle
