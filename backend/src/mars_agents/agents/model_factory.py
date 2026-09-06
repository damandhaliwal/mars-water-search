"""One fixed Gemini endpoint with no transport retries and paced request starts."""

from collections.abc import Callable
from pathlib import Path

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from smolagents import OpenAIModel
from smolagents.models import ChatMessage
from smolagents.monitoring import TokenUsage

GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/openai/"
ROOT_ENV = Path(__file__).resolve().parents[4] / ".env"


class GeminiConfigurationError(RuntimeError):
    """Safe configuration error suitable for an HTTP 503 response."""


class GeminiSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    gemini_api_key: SecretStr | None = Field(default=None, repr=False, exclude=True)
    gemini_model: str = "gemini-3.8-flash"
    gemini_temperature: float = Field(default=0, ge=0, le=2)
    gemini_max_concurrency: int = Field(default=4, ge=1, le=32)
    gemini_request_interval: float = Field(default=1, ge=0, allow_inf_nan=False)
    gemini_timeout: float = Field(default=45, gt=0, le=300)
    gemini_retries: int = Field(default=2, ge=0, le=2)

    @field_validator("gemini_model")
    @classmethod
    def flash_only(cls, value: str) -> str:
        import re

        if not re.fullmatch(r"gemini-(?:\d+(?:\.\d+)*-)?flash(?:-[a-z0-9]+)*", value):
            raise ValueError("GEMINI_MODEL must be a Gemini Flash model identifier")
        return value

    def ensure_configured(self) -> None:
        if self.gemini_api_key is None or not self.gemini_api_key.get_secret_value().strip():
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is required to step or run an experiment. "
                "Set it in the repository-root .env or environment and restart the backend."
            )


class GeminiModel(OpenAIModel):
    """OpenAIModel adapter that discards raw responses and tolerates absent usage.

    smolagents 1.26.0's OpenAIModel.generate retains the entire response and
    unconditionally reads response.usage. Use its request builder and real client,
    but retain only function calls and optional counts. Never parse text as actions.
    """

    before_request: Callable[[], None] | None = None

    def generate(self, messages, stop_sequences=None, tools_to_call_from=None, **kwargs):
        completion_kwargs = self._prepare_completion_kwargs(
            messages=messages,
            tools_to_call_from=tools_to_call_from,
            model=self.model_id,
            custom_role_conversions=self.custom_role_conversions,
            convert_images_to_image_urls=True,
            **kwargs,
        )
        # Gate immediately before the request, after constructing its payload.
        if self.before_request is not None:
            self.before_request()
        # Neither smolagents retryer nor OpenAI's retries wrap this request.
        response = self.client.chat.completions.create(**completion_kwargs)
        message = response.choices[0].message
        usage = response.usage
        return ChatMessage(
            role=message.role,
            tool_calls=message.tool_calls,
            token_usage=(
                TokenUsage(input_tokens=usage.prompt_tokens, output_tokens=usage.completion_tokens)
                if usage is not None
                else None
            ),
        )


def create_model(settings: GeminiSettings) -> GeminiModel:
    settings.ensure_configured()
    assert settings.gemini_api_key is not None
    return GeminiModel(
        model_id=settings.gemini_model,
        api_base=GEMINI_ENDPOINT,
        api_key=settings.gemini_api_key.get_secret_value(),
        temperature=settings.gemini_temperature,
        client_kwargs={"timeout": settings.gemini_timeout, "max_retries": 0},
        retry=False,
    )
