"""등락 색상 관례.

Streamlit 에 의존하지 않는다 — 노트북에서도 같은 색을 쓰기 위해 분리했다.

    kr     : 양수=적색, 음수=청색 (국내 시장 관례, 기본)
    global : 양수=청색, 음수=적색
"""
from __future__ import annotations

from .config import load_config

__all__ = ["COLOR_SCHEMES", "DEFAULT_SCHEME", "sign_colors", "sign_color",
           "SERIES_COLORS", "HIGHLIGHT", "NEUTRAL", "BM_COLOR"]

COLOR_SCHEMES = {
    "kr": {"positive": "#d32020", "negative": "#1d4ed8"},
    "global": {"positive": "#2563eb", "negative": "#dc2626"},
}
DEFAULT_SCHEME = "kr"

HIGHLIGHT = "#0f172a"   # 선택 모델 강조선 (부호와 무관한 색)
NEUTRAL = "#64748b"
BM_COLOR = "#94a3b8"

# 다중 시계열용 범주형 색상.
# 적색/청색은 부호(등락)를 뜻하므로 앞쪽에 두지 않는다 - 계열 구분과 혼동되지 않게.
SERIES_COLORS = [
    "#0f766e", "#7c3aed", "#b45309", "#0891b2", "#be185d",
    "#4d7c0f", "#475569", "#a16207", "#15803d", "#c2410c",
    "#1e40af", "#9f1239",
]


def sign_colors() -> dict:
    """설정에 따른 등락 색상. ``{"positive": ..., "negative": ...}``"""
    scheme = load_config().ui.get("color_convention", DEFAULT_SCHEME)
    return COLOR_SCHEMES.get(scheme, COLOR_SCHEMES[DEFAULT_SCHEME])


def sign_color(value) -> str:
    """값의 부호에 맞는 색."""
    colors = sign_colors()
    try:
        return colors["positive"] if float(value) >= 0 else colors["negative"]
    except (TypeError, ValueError):
        return NEUTRAL
