from __future__ import annotations

from dataclasses import dataclass


TICK_DEFAULT = 0.01


@dataclass(frozen=True)
class ClickMode:
    value: str
    label: str


def click_modes_for_order_type(order_type: str) -> list[ClickMode]:
    ot = str(order_type or "MARKET").upper()
    if ot == "MARKET":
        return [ClickMode("stop", "Stop loss"), ClickMode("target", "Take profit")]
    if ot in ("LIMIT", "STOP"):
        return [ClickMode("entry", "Entry"), ClickMode("stop", "Stop loss"), ClickMode("target", "Take profit")]
    if ot == "STOP_LIMIT":
        return [
            ClickMode("entry_stop", "Entry stop"),
            ClickMode("entry_limit", "Entry limit"),
            ClickMode("stop", "Stop loss"),
            ClickMode("target", "Take profit"),
        ]
    return [ClickMode("entry", "Entry"), ClickMode("stop", "Stop loss"), ClickMode("target", "Take profit")]


def draft_ticket_summary(
    *,
    side: str,
    order_type: str,
    qty: int | None,
    limit_px: float | None,
    stop_px: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    mark_price: float | None,
) -> str:
    s = str(side or "").upper()
    ot = str(order_type or "").upper()
    q = int(qty or 0)

    parts = []
    if s:
        parts.append(s)
    if q > 0:
        parts.append(str(q))
    parts.append(ot if ot else "—")

    if ot == "MARKET":
        pass
    elif ot == "LIMIT":
        if limit_px is not None:
            parts.append(f"@ {float(limit_px):.2f}")
    elif ot == "STOP":
        if stop_px is not None:
            parts.append(f"@ {float(stop_px):.2f}")
    elif ot == "STOP_LIMIT":
        if stop_px is not None and limit_px is not None:
            parts.append(f"STP {float(stop_px):.2f} / LMT {float(limit_px):.2f}")
        elif stop_px is not None:
            parts.append(f"STP {float(stop_px):.2f}")
        elif limit_px is not None:
            parts.append(f"LMT {float(limit_px):.2f}")

    if stop_loss is not None:
        parts.append(f"| SL {float(stop_loss):.2f}")
    if take_profit is not None:
        parts.append(f"| TP {float(take_profit):.2f}")
    if ot == "MARKET" and mark_price is not None:
        parts.append(f"(mark {float(mark_price):.2f})")

    return " ".join(parts).strip()


def mode_help_text(*, order_type: str, click_mode: str) -> str:
    ot = str(order_type or "MARKET").upper()
    m = str(click_mode or "")
    # Keep this short and operational; this is UI microcopy.
    if ot == "MARKET":
        if m == "stop":
            return "Editing: Stop loss — click chart to set; drag the Draft SL line to fine-tune."
        if m == "target":
            return "Editing: Take profit — click chart to set; drag the Draft TP line to fine-tune."
        return "Market: chart edits SL/TP only."

    if ot == "STOP_LIMIT":
        if m == "entry_stop":
            return "Editing: Entry stop — click to set; drag the Draft entry stop line."
        if m == "entry_limit":
            return "Editing: Entry limit — click to set; drag the Draft entry limit line."
        if m == "stop":
            return "Editing: Stop loss — click to set; drag the Draft SL line."
        if m == "target":
            return "Editing: Take profit — click to set; drag the Draft TP line."
        return "STOP_LIMIT: pick which leg to edit, then click/drag on chart."

    # LIMIT / STOP
    if m == "entry":
        return "Editing: Entry — click chart to set; drag the Draft entry line to fine-tune."
    if m == "stop":
        return "Editing: Stop loss — click chart to set; drag the Draft SL line to fine-tune."
    if m == "target":
        return "Editing: Take profit — click chart to set; drag the Draft TP line to fine-tune."
    return "Click/drag on chart to build the draft ticket."

