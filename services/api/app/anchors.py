"""Anchor shapes shared by the API, the worker, and the evidence check.

A frame that is absent from the saved list was not annotated. Older rows used
`box` for a drag and `not_visible` for every other frame, including ones nobody
looked at. Those old rows are described, not rewritten.
"""

from __future__ import annotations


def present_anchor(raw: dict) -> dict:
    state = raw.get("state")
    source = raw.get("source")
    if state == "box":
        state = "located"
        source = source or "manual"
    if state == "located" and source not in ("manual", "estimated"):
        source = "manual"
    box = raw.get("box")
    if state == "not_visible":
        box = None
        source = None
    return {
        "frame_id": raw["frame_id"],
        "state": state,
        "source": source,
        "box": box,
        "method": raw.get("method"),
        "reason": raw.get("reason"),
        "explicit": bool(raw.get("explicit")),
    }


def review_reasons(raw_anchors: list[dict], identity_uncertain: bool) -> list[str]:
    reasons: list[str] = []
    if identity_uncertain:
        reasons.append(
            "A previous save marked identity uncertain for the whole clip. "
            "That flag no longer blocks an observation. Check the frames and save the target again."
        )
    hidden = [
        anchor["frame_id"]
        for anchor in raw_anchors
        if anchor.get("state") == "not_visible" and not anchor.get("explicit")
    ]
    if hidden:
        listed = ", ".join(hidden)
        reasons.append(
            f"Not-visible marks on {listed} were saved when untouched frames could be filled in bulk. "
            "Clear any frame you did not check."
        )
    return reasons
