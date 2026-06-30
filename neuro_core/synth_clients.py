import base64


def _is_image_input_error(exc):
    """True for the OpenRouter rejection of figure images by a text-only model
    (404 'No endpoints found that support image input', e.g. z-ai/glm-5.2)."""
    return "image input" in str(exc).lower()


class OpenRouterSynthClient:
    """OpenAI-compatible (OpenRouter) backend. Fallback when GCP credit runs out."""

    def __init__(self, api_key, model, client=None):
        self.api_key = api_key
        self.model = model
        self._client = client
        # Optimistically send figure images; flipped off the first time the model
        # rejects them (text-only models like z-ai/glm-5.2 have no image endpoint).
        self._supports_images = True

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url="https://openrouter.ai/api/v1",
                                  api_key=self.api_key)
        return self._client

    def generate(self, system, user, images):
        send = images if self._supports_images else []
        try:
            return self._complete(system, user, send)
        except Exception as e:  # scoped below: re-raised unless it's the image case
            if self._supports_images and images and _is_image_input_error(e):
                # Text-only model: drop the figure images and retry. The figure
                # captions are already in the prompt text, so citations are
                # unaffected. Remember it so later calls skip images upfront.
                self._supports_images = False
                return self._complete(system, user, [])
            raise

    def _complete(self, system, user, images):
        content = [{"type": "text", "text": user}]
        for img in images:
            b64 = base64.b64encode(img).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        )
        return resp.choices[0].message.content or ""

    def generate_stream(self, system, user, images):
        """Yield answer text deltas (concatenation == generate()'s text). Respects the
        learned text-only flag. A cold image rejection surfaces as an exception that the
        caller degrades to the blocking generate() path, which owns the retry + flag flip.
        # ponytail: no mid-stream image retry — the blocking fallback already self-heals."""
        send = images if self._supports_images else []
        content = [{"type": "text", "text": user}]
        for img in send:
            b64 = base64.b64encode(img).decode("ascii")
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        stream = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


class LocalSynthClient(OpenRouterSynthClient):
    """Local OpenAI-compatible backend (Ollama / llama.cpp). Runs on your own GPU:
    no passages/figures leave the machine, no cloud spend. Text-only by design — a
    local text model can't use figure images, but the figure sources/captions are
    already in the prompt text, so citations are unaffected. api_key is a dummy the
    local server ignores (the openai client requires a non-empty value)."""

    def __init__(self, base_url, model, api_key="local", client=None):
        super().__init__(api_key=api_key, model=model, client=client)
        self.base_url = base_url

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url=self.base_url, api_key=self.api_key)
        return self._client

    def generate(self, system, user, images):
        resp = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return resp.choices[0].message.content or ""

    def generate_stream(self, system, user, images):
        """Text-only streaming (mirrors generate(): a local text model ignores figure images)."""
        stream = self.client.chat.completions.create(
            model=self.model,
            temperature=0.1,
            stream=True,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta


class VertexSynthClient:
    """Vertex AI Gemini backend (default). Spends the GCP credit.
    Auth via Application Default Credentials (gcloud auth application-default login).
    Targets google-genai >= 1.0."""

    def __init__(self, project, location, model, client=None, timeout_ms=None):
        self.project = project
        self.location = location
        self.model = model
        self.timeout_ms = timeout_ms
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google import genai
            from google.genai import types
            http_options = (types.HttpOptions(timeout=self.timeout_ms)
                            if self.timeout_ms else None)
            self._client = genai.Client(vertexai=True, project=self.project,
                                        location=self.location,
                                        http_options=http_options)
        return self._client

    def generate(self, system, user, images):
        from google.genai import types
        parts = [types.Part.from_text(text=user)]
        for img in images:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
        resp = self.client.models.generate_content(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=0.1),
        )
        return resp.text or ""

    def generate_stream(self, system, user, images):
        """Yield answer text deltas (concatenation == generate()'s text)."""
        from google.genai import types
        parts = [types.Part.from_text(text=user)]
        for img in images:
            parts.append(types.Part.from_bytes(data=img, mime_type="image/png"))
        stream = self.client.models.generate_content_stream(
            model=self.model,
            contents=[types.Content(role="user", parts=parts)],
            config=types.GenerateContentConfig(
                system_instruction=system, temperature=0.1),
        )
        for chunk in stream:
            if getattr(chunk, "text", None):
                yield chunk.text


def make_synth_client(config):
    if config.synth_provider == "local":
        return LocalSynthClient(config.local_base_url, config.local_model)
    if config.synth_provider == "openrouter":
        return OpenRouterSynthClient(config.openrouter_api_key,
                                     config.openrouter_model)
    return VertexSynthClient(config.google_cloud_project,
                             config.google_cloud_location,
                             config.vertex_model)


def make_analyze_client(config):
    """Client for the lightweight query-disambiguation ("analyze") step.

    Disambiguation is a constrained classification task, not synthesis, so it defaults to a
    cheaper/faster model (config ANALYZE_MODEL) — benchmarked indistinguishable in answer
    quality but markedly faster. When ANALYZE_MODEL is empty it falls back to the synthesis
    client, preserving the historical single-client behavior."""
    model = getattr(config, "analyze_model", "") or ""
    if not model:
        return make_synth_client(config)
    provider = getattr(config, "analyze_provider", "") or config.synth_provider
    if provider == "local":
        return LocalSynthClient(config.local_base_url, model)
    if provider == "openrouter":
        return OpenRouterSynthClient(config.openrouter_api_key, model)
    return VertexSynthClient(config.google_cloud_project,
                             config.google_cloud_location, model)
