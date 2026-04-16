from __future__ import annotations

from typing import Any

import httpx

from schemas import EmbeddingItem, RiskFlag

OLLAMA_BASE_URL = "http://localhost:11434"
CHAT_MODEL = "qwen3:4b"
EMBEDDING_MODEL = "qwen3-embedding:0.6b"


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str = OLLAMA_BASE_URL, timeout: float = 20.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def embed_texts(self, texts: list[str]) -> list[EmbeddingItem]:
        embeddings: list[EmbeddingItem] = []
        with httpx.Client(timeout=self._timeout) as client:
            for text in texts:
                payload = {"model": EMBEDDING_MODEL, "input": text}
                data = self._post_json(client, "/api/embed", payload, retries=1)
                vectors = data.get("embeddings")
                if not isinstance(vectors, list) or not vectors:
                    raise OllamaError("Embedding response was empty.")
                vector = vectors[0]
                if not isinstance(vector, list):
                    raise OllamaError("Embedding response format was invalid.")
                embeddings.append(EmbeddingItem(text=text, vector=[float(value) for value in vector]))
        return embeddings

    def generate_summary(self, prompt: str) -> str:
        payload = {
            "model": CHAT_MODEL,
            "prompt": prompt,
            "stream": False,
        }
        with httpx.Client(timeout=self._timeout) as client:
            data = self._post_json(client, "/api/generate", payload, retries=0)

        response = data.get("response")
        if not isinstance(response, str) or not response.strip():
            raise OllamaError("Summary response was empty.")
        return response.strip()

    def rewrite_risk_flags(self, risk_flags: list[RiskFlag]) -> list[RiskFlag]:
        if not risk_flags:
            return risk_flags
        prompt = (
            "Rewrite each risk flag message to be concise and recruiter-friendly.\n"
            "Return one line per item in the same order.\n\n"
            + "\n".join(f"{item.category}: {item.message}" for item in risk_flags)
        )
        text = self.generate_summary(prompt)
        lines = [line.strip(" -") for line in text.splitlines() if line.strip()]
        if len(lines) != len(risk_flags):
            return risk_flags
        return [
            RiskFlag(category=item.category, message=lines[index])
            for index, item in enumerate(risk_flags)
        ]

    def _post_json(
        self,
        client: httpx.Client,
        path: str,
        payload: dict[str, Any],
        retries: int,
    ) -> dict[str, Any]:
        attempts = retries + 1
        last_error: Exception | None = None
        for _ in range(attempts):
            try:
                response = client.post(f"{self._base_url}{path}", json=payload)
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise OllamaError("Ollama response format was invalid.")
                return data
            except (httpx.HTTPError, ValueError, OllamaError) as exc:
                last_error = exc
        raise OllamaError(f"Ollama request failed: {last_error}") from last_error
