"""Gemini client supporting TWO auth modes behind one interface.

  - service_account: Vertex AI, credentials loaded from a service-account JSON file
                     (project_id read from the file). Used during development/testing.
  - api_key:         Gemini Developer API with an API key. Used for the submitted build.

Both expose the identical `generate_structured(...)`; callers (GeminiExtractor,
GeminiSemanticMapper) are auth-agnostic. Google libraries are imported lazily so the
deterministic eval/test path never needs them installed.
"""

from __future__ import annotations

import json
import time
from typing import Any, Optional

from ..config import AppConfig


class LLMError(Exception):
    pass


class LLMAuthError(LLMError):
    pass


class LLMTimeoutError(LLMError):
    pass


class LLMResponseParseError(LLMError):
    pass


def build_gemini_client(cfg: AppConfig):
    """Factory: returns a configured google.genai Client for the selected auth mode."""
    from google import genai  # lazy
    from google.genai import types

    http = types.HttpOptions(timeout=cfg.request_timeout_ms)
    if cfg.auth_mode == "api_key":
        if not cfg.api_key:
            raise LLMAuthError("GEMINI_AUTH_MODE=api_key but GEMINI_API_KEY is not set")
        return genai.Client(api_key=cfg.api_key, http_options=http)

    # service_account (Vertex)
    from google.oauth2 import service_account

    if not cfg.sa_path:
        raise LLMAuthError("GEMINI_AUTH_MODE=service_account but GOOGLE_APPLICATION_CREDENTIALS is not set")
    creds = service_account.Credentials.from_service_account_file(
        cfg.sa_path, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    with open(cfg.sa_path, encoding="utf-8") as f:
        project_id = json.load(f)["project_id"]
    return genai.Client(
        vertexai=True, project=project_id, location=cfg.location,
        credentials=creds, http_options=http,
    )


class GeminiClient:
    def __init__(self, cfg: AppConfig, client: Optional[Any] = None):
        self.cfg = cfg
        self._client = client  # lazily built on first use if None

    @property
    def client(self):
        if self._client is None:
            self._client = build_gemini_client(self.cfg)
        return self._client

    def generate_structured(
        self,
        prompt: str,
        response_schema: type,
        parts: Optional[list[tuple[bytes, str]]] = None,
        max_retries: int = 1,
    ) -> dict:
        """Generate JSON conforming to a Pydantic `response_schema`. `parts` is a list of
        (bytes, mime_type) for images/PDFs. Returns a plain dict.

        Raises LLMTimeoutError / LLMAuthError / LLMResponseParseError / LLMError.
        """
        from google.genai import types
        from google.genai import errors

        contents: list[Any] = [prompt]
        for data, mime in (parts or []):
            contents.append(types.Part.from_bytes(data=data, mime_type=mime))

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=response_schema,
            temperature=0,
        )

        attempt = 0
        while True:
            try:
                resp = self.client.models.generate_content(
                    model=self.cfg.model, contents=contents, config=config
                )
                return self._parse(resp, response_schema)
            except errors.ClientError as exc:
                if getattr(exc, "code", None) == 429 and attempt < max_retries:
                    time.sleep(2 ** attempt)
                    attempt += 1
                    continue
                if getattr(exc, "code", None) in (401, 403):
                    raise LLMAuthError(str(exc)) from exc
                raise LLMError(str(exc)) from exc
            except errors.ServerError as exc:
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    attempt += 1
                    continue
                raise LLMError(str(exc)) from exc
            except Exception as exc:  # auth refresh, timeouts, network
                name = type(exc).__name__.lower()
                if "timeout" in name or "deadline" in name:
                    raise LLMTimeoutError(str(exc)) from exc
                if "refresh" in name or "credential" in name or "auth" in name:
                    raise LLMAuthError(str(exc)) from exc
                raise LLMError(str(exc)) from exc

    @staticmethod
    def _parse(resp: Any, schema: type) -> dict:
        parsed = getattr(resp, "parsed", None)
        if parsed is not None:
            if hasattr(parsed, "model_dump"):
                return parsed.model_dump()
            if isinstance(parsed, dict):
                return parsed
        text = getattr(resp, "text", None)
        if not text:
            raise LLMResponseParseError("Empty response from model")
        try:
            if hasattr(schema, "model_validate_json"):
                return schema.model_validate_json(text).model_dump()
            return json.loads(text)
        except Exception as exc:
            raise LLMResponseParseError(f"Could not parse model JSON: {exc}") from exc
