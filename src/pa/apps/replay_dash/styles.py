from __future__ import annotations


def palette() -> dict[str, str]:
    return {
        "bg": "#ffffff",
        "panel": "#f8fafc",
        "text": "#0f172a",
        "muted": "#475569",
        "border": "rgba(2,6,23,0.10)",
        "accent": "#2563eb",
        "ok": "#16a34a",
        "bad": "#dc2626",
    }


def panel_style(colors: dict[str, str]) -> dict:
    return {
        "background": colors["panel"],
        "border": f"1px solid {colors['border']}",
        "borderRadius": "12px",
        "padding": "12px",
        "boxShadow": "0 1px 2px rgba(2,6,23,0.05)",
    }


def label_style(colors: dict[str, str]) -> dict:
    return {"fontSize": "12px", "color": colors["muted"], "marginBottom": "6px"}


def input_style() -> dict:
    return {"width": "100%"}


def btn_style(colors: dict[str, str]) -> dict:
    return {
        "padding": "8px 10px",
        "borderRadius": "10px",
        "border": f"1px solid {colors['border']}",
        "background": "#ffffff",
        "color": colors["text"],
        "fontSize": "12px",
        "cursor": "pointer",
    }


def btn_primary_style(colors: dict[str, str]) -> dict:
    base = btn_style(colors)
    return {**base, "background": colors["accent"], "color": "white", "border": "none", "fontWeight": 700}

