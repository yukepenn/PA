from __future__ import annotations


def ticket_context_hints(
    *,
    side: str,
    order_type: str,
    limit_px: float | None,
    stop_px: float | None,
    stop_loss: float | None,
    take_profit: float | None,
    mark_price: float | None,
) -> list[str]:
    """Lightweight explanatory hints — never replaces validation rules."""

    hints: list[str] = []
    s = str(side or "").upper()
    ot = str(order_type or "").upper()

    if ot == "MARKET":
        hints.append("MARKET entry is immediate when eligible (subject to activation rules); SL/TP only shape risk after entry.")

    # Short semantics (often confusing with LIMIT vs STOP triggers)
    if s == "SELL_SHORT":
        if ot == "LIMIT":
            hints.append(
                "SHORT LIMIT @ x is a resting sell-above order: short when price trades at x or higher (better fills can occur above x)."
            )
        if ot == "STOP":
            hints.append(
                "SHORT STOP @ x triggers when price trades at x or lower (breakdown / continuation short style)."
            )
        if ot == "STOP_LIMIT":
            hints.append(
                "SHORT STOP_LIMIT triggers on the STOP leg first; the LIMIT leg constrains the executable fill."
            )

        # Marketable retracement heuristic (minimal, non-blocking): short limit above current mark implies selling into strength / pullback short.
        if ot == "LIMIT" and limit_px is not None and mark_price is not None:
            try:
                lx = float(limit_px)
                mk = float(mark_price)
                if lx >= mk:
                    hints.append(f"SHORT LIMIT ({lx:.2f}) is above current ref ({mk:.2f}) — retracement/add-to-strength entry, not a downside STOP trigger.")
            except Exception:
                pass

        if ot == "STOP" and stop_px is not None and mark_price is not None:
            try:
                sx = float(stop_px)
                mk = float(mark_price)
                if sx <= mk:
                    hints.append(f"SHORT STOP ({sx:.2f}) below ref ({mk:.2f}) — breakout-style trigger when weakness appears.")
            except Exception:
                pass

    # Long analogous (lighter)
    if s == "BUY":
        if ot == "LIMIT":
            hints.append(
                "LONG LIMIT @ x is a resting bid: long when price trades at x or lower (better fills can occur below x)."
            )
        if ot == "STOP":
            hints.append(
                "LONG STOP @ x triggers when price trades at x or higher (continuation / breakout style)."
            )

        if ot == "LIMIT" and limit_px is not None and mark_price is not None:
            try:
                lx = float(limit_px)
                mk = float(mark_price)
                if lx <= mk:
                    hints.append(f"LONG LIMIT ({lx:.2f}) is below current ref ({mk:.2f}) — dip-buy / retracement bid, not an upside breakout STOP trigger.")
            except Exception:
                pass

    # RR sanity nudge (purely explanatory)
    if stop_loss is not None and take_profit is not None:
        hints.append(
            "RR zones visualize planned brackets from your ticket — actual entry/exit prices come from fills shown on markers."
        )

    return hints
