from app.config import Settings
from app.db import Database, new_id


def estimate_usd(settings: Settings, input_tokens: int) -> float:
    output_tokens = settings.max_output_tokens
    return (input_tokens * settings.price_input_per_mtok + output_tokens * settings.price_output_per_mtok) / 1_000_000


def actual_usd(settings: Settings, usage: dict) -> float:
    input_tokens = int(usage.get("input_tokens") or 0)
    output_tokens = int(usage.get("output_tokens") or 0)
    return (input_tokens * settings.price_input_per_mtok + output_tokens * settings.price_output_per_mtok) / 1_000_000


def can_reserve(db: Database, settings: Settings, job_id: str, amount: float) -> str | None:
    if db.job_committed_usd(job_id) + amount > settings.job_budget_usd + 1e-9:
        return "This window is over the per-run cost limit. Shorten it and try again."
    if db.committed_usd() + db.reserved_usd() + amount > settings.app_budget_usd + 1e-9:
        return "The session cost limit has been reached. No further model calls will be made."
    return None


def reserve(db: Database, job_id: str, amount: float) -> str:
    reservation_id = new_id("rsv")
    db.add_budget(reservation_id=reservation_id, job_id=job_id, kind="reserve", amount_usd=amount)
    return reservation_id


def reconcile(db: Database, reservation_id: str, job_id: str, amount: float, usage: dict) -> None:
    db.add_budget(
        reservation_id=reservation_id,
        job_id=job_id,
        kind="reconcile",
        amount_usd=amount,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
    )


def release(db: Database, reservation_id: str, job_id: str, amount: float) -> None:
    db.add_budget(reservation_id=reservation_id, job_id=job_id, kind="release", amount_usd=amount)
