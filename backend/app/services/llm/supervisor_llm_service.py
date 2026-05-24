"""Supervisor LLM service for reflection using an OpenAI-compatible API."""

from __future__ import annotations

from openai import OpenAI

from app.core.config import settings


class SupervisorLLMService:
    """Call the dedicated supervisor/reflection model without affecting NL2SQL generation."""

    def __init__(self) -> None:
        self.model = settings.scopedashboard_model
        self.temperature = settings.scopedashboard_temperature
        self.client = OpenAI(
            api_key=settings.scopedashboard_api_key,
            base_url=settings.scopedashboard_base_url,
            timeout=settings.scopedashboard_request_timeout,
        )

    @property
    def is_configured(self) -> bool:
        return bool(settings.scopedashboard_api_key)

    def reflect(self, system_prompt: str, user_payload: str) -> str:
        """Return raw supervisor model output as text."""
        response = self.client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            timeout=settings.scopedashboard_request_timeout,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_payload},
            ],
        )
        return response.choices[0].message.content or ""
