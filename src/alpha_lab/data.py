"""Research-only daily bars and explicit data integrity checks."""
from __future__ import annotations

import csv
from math import isfinite
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class Bar:
    symbol: str
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float


def validate_bars(bars: list[Bar]) -> list[Bar]:
    if not bars:
        raise ValueError("NO_BARS")
    symbol = bars[0].symbol
    previous = ""
    for bar in bars:
        if bar.symbol != symbol or not (len(bar.symbol) == 6 and bar.symbol.isdigit()):
            raise ValueError("MIXED_OR_INVALID_SYMBOL")
        try:
            date.fromisoformat(bar.date)
        except ValueError as exc:
            raise ValueError("INVALID_DATE") from exc
        if bar.date <= previous:
            raise ValueError("OUT_OF_ORDER_OR_DUPLICATE_DATE")
        previous = bar.date
        if not all(isfinite(value) for value in (bar.open, bar.high, bar.low, bar.close, bar.volume)):
            raise ValueError("NONFINITE_DATA")
        if min(bar.open, bar.high, bar.low, bar.close) <= 0:
            raise ValueError("NONPOSITIVE_PRICE")
        if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
            raise ValueError("INVALID_OHLC")
        if bar.volume < 0:
            raise ValueError("NEGATIVE_VOLUME")
    return bars


def load_csv(path: str | Path) -> list[Bar]:
    with open(path, encoding="utf-8-sig", newline="") as stream:
        records = list(csv.DictReader(stream))
    try:
        bars = [
            Bar(
                symbol=str(row["symbol"]).zfill(6),
                date=row["date"],
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            for row in records
        ]
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("INVALID_CSV_SCHEMA_OR_VALUE") from exc
    return validate_bars(bars)


def save_csv(bars: list[Bar], path: str | Path) -> None:
    validate_bars(bars)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(Bar.__dataclass_fields__))
        writer.writeheader()
        for bar in bars:
            writer.writerow(vars(bar))


def download_akshare(symbol: str, start: str, end: str) -> list[Bar]:
    """Unadjusted data ONLY. Historical corporate actions are not modelled yet."""
    if not (symbol.isdigit() and len(symbol) == 6):
        raise ValueError("INVALID_SYMBOL")
    if not (len(start) == len(end) == 8 and start.isdigit() and end.isdigit() and start <= end):
        raise ValueError("INVALID_DATE_RANGE")
    try:
        import akshare as ak
    except ImportError as exc:
        raise RuntimeError("AKSHARE_NOT_INSTALLED: pip install -e '.[data]'") from exc
    frame = ak.stock_zh_a_hist(
        symbol=symbol, period="daily", start_date=start, end_date=end, adjust=""
    )
    if frame is None or frame.empty:
        raise ValueError("PROVIDER_RETURNED_NO_DATA")
    bars = [
        Bar(
            symbol=symbol,
            date=str(row["日期"])[:10],
            open=float(row["开盘"]),
            high=float(row["最高"]),
            low=float(row["最低"]),
            close=float(row["收盘"]),
            volume=float(row["成交量"]),
        )
        for _, row in frame.iterrows()
    ]
    return validate_bars(bars)
