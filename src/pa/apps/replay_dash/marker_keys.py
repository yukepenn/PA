from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarkerKey:
    scope: str  # "draft" | "sim"
    field: str
    entity_id: str  # "draft" or order_id


def encode_marker_key(*, scope: str, field: str, entity_id: str) -> str:
    """
    Stable, parseable key stored in Plotly shape/annotation `name`.
    Convention: "<scope>:<field>:<entity_id>"
    """
    s = str(scope or "").strip()
    f = str(field or "").strip()
    eid = str(entity_id or "").strip()
    if not s or not f or not eid:
        raise ValueError("encode_marker_key requires scope, field, and entity_id")
    if ":" in s or ":" in f or ":" in eid:
        raise ValueError("encode_marker_key components must not contain ':'")
    return f"{s}:{f}:{eid}"


def decode_marker_key(name: str | None) -> MarkerKey | None:
    n = str(name or "").strip()
    if not n or ":" not in n:
        return None
    parts = n.split(":")
    if len(parts) < 3:
        return None
    scope = parts[0]
    field = parts[1]
    entity_id = ":".join(parts[2:])  # tolerate future extension
    if not scope or not field or not entity_id:
        return None
    return MarkerKey(scope=scope, field=field, entity_id=entity_id)

