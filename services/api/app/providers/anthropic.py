import json
import logging
from pathlib import Path

import anthropic
from pydantic import ValidationError

from app.providers.base import EvidenceProvider, ProviderCallResult, ProviderError
from app.schemas import ProviderEvidence

log = logging.getLogger("secondlook.provider")


def _usage(value: object) -> dict:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return {
        "input_tokens": int(getattr(value, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(value, "output_tokens", 0) or 0),
    }


def _retry_after(exc: anthropic.APIStatusError) -> float | None:
    header = ""
    response = getattr(exc, "response", None)
    if response is not None:
        header = response.headers.get("retry-after", "")
    try:
        return float(header) if header else None
    except ValueError:
        return None


class AnthropicProvider(EvidenceProvider):
    label = "live"

    def __init__(self, api_key: str, model: str, timeout: float, max_output_tokens: int) -> None:
        # SDK retries are off so this app can count and cap every attempt itself.
        self.client = anthropic.Anthropic(api_key=api_key, timeout=timeout, max_retries=0)
        self.model = model
        self.max_output_tokens = max_output_tokens

    def count_tokens(self, system: str, messages: list[dict]) -> int:
        try:
            counted = self.client.messages.count_tokens(model=self.model, system=system, messages=messages)
        except Exception as exc:
            raise self._translate(exc) from None
        return int(counted.input_tokens)

    def extract(self, system: str, messages: list[dict]) -> ProviderCallResult:
        try:
            response = self.client.messages.parse(
                model=self.model,
                max_tokens=self.max_output_tokens,
                system=system,
                messages=messages,
                output_format=ProviderEvidence,
            )
        except ValidationError as exc:
            brief = []
            for item in exc.errors()[:4]:
                entry = {"loc": list(item.get("loc", ())), "type": item.get("type"), "msg": item.get("msg")}
                raw = item.get("input")
                if isinstance(raw, str):
                    entry["input_head"] = raw[:500]
                    entry["input_tail"] = raw[-300:]
                brief.append(entry)
            log.warning("evidence schema mismatch %s", brief)
            Path("data").mkdir(exist_ok=True)
            Path("data/last_schema_error.json").write_text(json.dumps(brief), encoding="utf-8")
            raise ProviderError(
                "malformed_output",
                "The model response did not match the evidence schema.",
                retryable=False,
                billed=True,
            ) from None
        except Exception as exc:
            raise self._translate(exc) from None
        usage = _usage(response.usage)
        parsed = response.parsed_output
        if parsed is None:
            stop = response.stop_reason
            if stop == "refusal":
                raise ProviderError(
                    "provider_refusal",
                    "The model declined this window. Try a different interval.",
                    billed=True,
                    usage=usage,
                )
            if stop == "max_tokens":
                raise ProviderError(
                    "provider_truncated",
                    "The model response was cut off. Retry this window.",
                    retryable=True,
                    billed=True,
                    usage=usage,
                )
            raise ProviderError(
                "malformed_output",
                "The model response did not match the evidence schema.",
                billed=True,
                usage=usage,
            )
        raw = response.model_dump() if hasattr(response, "model_dump") else {"id": response.id}
        return ProviderCallResult(
            parsed=parsed,
            model=response.model,
            usage=usage,
            stop_reason=response.stop_reason,
            request_id=response.id,
            raw=raw,
        )

    def _translate(self, exc: Exception) -> ProviderError:
        log.info("provider error type=%s", type(exc).__name__)
        if isinstance(exc, anthropic.AuthenticationError):
            return ProviderError(
                "provider_auth",
                "The API key was rejected. Check ANTHROPIC_API_KEY on the server.",
            )
        if isinstance(exc, anthropic.PermissionDeniedError):
            return ProviderError(
                "provider_auth",
                "This API key cannot use the configured model.",
            )
        if isinstance(exc, anthropic.NotFoundError):
            return ProviderError(
                "provider_model_unavailable",
                f"The model {self.model} is not available on this account. "
                "Set ANTHROPIC_MODEL to an image-capable model you can access. "
                "The app will not switch models on its own.",
            )
        if isinstance(exc, anthropic.RateLimitError):
            return ProviderError(
                "provider_rate_limited",
                "The model service is rate limiting requests. Wait a moment and retry this window.",
                retryable=True,
                retry_after=_retry_after(exc),
            )
        if isinstance(exc, anthropic.APITimeoutError):
            return ProviderError(
                "provider_timeout",
                "The model took too long. Retry this window.",
                retryable=True,
                billed=True,
            )
        if isinstance(exc, anthropic.APIConnectionError):
            return ProviderError(
                "provider_unavailable",
                "The model service could not be reached. Retry this window.",
                retryable=True,
            )
        if isinstance(exc, anthropic.InternalServerError):
            return ProviderError(
                "provider_unavailable",
                "The model service failed. Retry this window.",
                retryable=True,
                billed=True,
            )
        if isinstance(exc, anthropic.BadRequestError):
            log.warning("provider rejected the request: %s", str(exc)[:400])
            return ProviderError(
                "provider_bad_request",
                "The model rejected the request. Confirm the configured model accepts images and structured output.",
            )
        if isinstance(exc, ProviderError):
            return exc
        return ProviderError(
            "provider_unavailable",
            "The model request failed. Retry this window.",
            retryable=True,
        )
