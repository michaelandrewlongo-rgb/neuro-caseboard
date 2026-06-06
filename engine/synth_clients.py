import base64


class OpenRouterSynthClient:
    """OpenAI-compatible (OpenRouter) backend. Fallback when GCP credit runs out."""

    def __init__(self, api_key, model, client=None):
        self.api_key = api_key
        self.model = model
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from openai import OpenAI
            self._client = OpenAI(base_url="https://openrouter.ai/api/v1",
                                  api_key=self.api_key)
        return self._client

    def generate(self, system, user, images):
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


class VertexSynthClient:
    """Vertex AI Gemini backend (default). Spends the GCP credit.
    Auth via Application Default Credentials (gcloud auth application-default login).
    Targets google-genai >= 1.0."""

    def __init__(self, project, location, model, client=None):
        self.project = project
        self.location = location
        self.model = model
        self._client = client

    @property
    def client(self):
        if self._client is None:
            from google import genai
            self._client = genai.Client(vertexai=True, project=self.project,
                                        location=self.location)
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


def make_synth_client(config):
    if config.synth_provider == "openrouter":
        return OpenRouterSynthClient(config.openrouter_api_key,
                                     config.openrouter_model)
    return VertexSynthClient(config.google_cloud_project,
                             config.google_cloud_location,
                             config.vertex_model)
