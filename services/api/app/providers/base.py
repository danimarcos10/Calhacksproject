from dataclasses import dataclass

from app.schemas import ProviderEvidence


@dataclass
class ProviderCallResult:
    parsed: ProviderEvidence
    model: str
    usage: dict
    stop_reason: str | None
    request_id: str | None
    raw: dict


class ProviderError(Exception):
    def __init__(
        self,
        code: str,
        user_message: str,
        *,
        retryable: bool = False,
        billed: bool = False,
        usage: dict | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(user_message)
        self.code = code
        self.user_message = user_message
        self.retryable = retryable
        self.billed = billed
        self.usage = usage or {}
        self.retry_after = retry_after


class EvidenceProvider:
    """The worker calls this. A live failure must not swap in another implementation."""

    label = "live"

    def count_tokens(self, system: str, messages: list[dict]) -> int:
        raise NotImplementedError

    def extract(self, system: str, messages: list[dict]) -> ProviderCallResult:
        raise NotImplementedError
