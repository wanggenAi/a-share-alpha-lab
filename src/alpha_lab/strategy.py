"""Simple, falsifiable daily trend-pullback hypothesis."""
from __future__ import annotations

from dataclasses import dataclass
from .data import Bar


@dataclass(frozen=True)
class Signal:
    symbol: str
    asof: str
    lower: float
    upper: float
    reference_close: float
    strategy: str = "trend_pullback_v01"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def detect(bars: list[Bar]) -> Signal | None:
    """Uses only observations at or before the returned as-of session."""
    if len(bars) < 65 or bars[-1].volume <= 0:
        return None
    closes = [bar.close for bar in bars]
    ma20 = _mean(closes[-20:])
    ma60 = _mean(closes[-60:])
    old_ma60 = _mean(closes[-65:-5])
    recent_high = max(bar.high for bar in bars[-10:])
    last, prev = bars[-1], bars[-2]
    if not (
        ma20 > ma60
        and ma60 > old_ma60
        and abs(last.close / ma20 - 1) <= 0.03
        and (recent_high - last.close) / recent_high >= 0.02
        and last.close > prev.close
    ):
        return None
    return Signal(
        symbol=last.symbol,
        asof=last.date,
        lower=round(ma20 * 0.99, 2),
        upper=round(ma20 * 1.02, 2),
        reference_close=last.close,
    )
