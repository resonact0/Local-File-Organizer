"""Drop-in replacements for nexa.gguf's NexaTextInference/NexaVLMInference,
backed by a local Ollama server instead of the (now defunct) Nexa SDK.

Exposes the same call shapes the rest of the codebase already relies on:
  - text_inference.create_completion(prompt) -> {'choices': [{'text': ...}]}
  - image_inference._chat(prompt, image_path) -> generator of
      {'choices': [{'delta': {'content': ...}}]}
"""

import base64
import ollama


class OllamaTextInference:
    def __init__(self, model="llama3.2:3b", host="http://localhost:11434", **_):
        self.model = model
        self.client = ollama.Client(host=host)

    def create_completion(self, prompt):
        response = self.client.generate(model=self.model, prompt=prompt, stream=False)
        return {'choices': [{'text': response['response']}]}


class OllamaVLMInference:
    def __init__(self, model="llava:7b", host="http://localhost:11434", **_):
        self.model = model
        self.client = ollama.Client(host=host)

    def _chat(self, prompt, image_path):
        with open(image_path, 'rb') as f:
            image_b64 = base64.b64encode(f.read()).decode('utf-8')
        response = self.client.generate(
            model=self.model, prompt=prompt, images=[image_b64], stream=False
        )
        yield {'choices': [{'delta': {'content': response['response']}}]}
