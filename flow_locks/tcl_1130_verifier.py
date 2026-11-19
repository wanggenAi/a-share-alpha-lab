"""Research-only TCL 000100, Nov 19 2026, 11:30 same-minute volume audit.

Uses public 5-minute data (Eastmoney; Sina fallback). All assertions fail closed.
Does not equate third-party fund-flow to Compass proprietary 3-day model.
No holdings, trades or credentials.
"""
from __future__ import annotations
import json
import math
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

CN = ZoneInfo("Asia/Shanghai")
SYMBOL = "000100"
ASOF = datetime(2026, 11, 19, 11, 31, tzinfo=CN)
EXPECTED_HANDS = 178.73 * 10000  # screenshot 11:30: 178.73 万手
CHECKPOINT = "11:30"
HISTORY_DAYS = 20


def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; ResearchVerifier/1.0)",
        "Accept": "application/json,text/plain,*/*",
        "Referer": "https://finance.sina.com.cn/" if "sina" in url else "https://quote.eastmoney.com/",
    })
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(4_000_000).decode("utf-8", "replace")
    return data


def eastmoney():
    from flow_locks.activity import five_minute_volume
    return five_minute_volume(SYMBOL), "Eastmoney public 5-minute klines", 1


def sina():
    from flow_locks.activity import LABELS
    q = urllib.parse.urlencode({
        "symbol": "sz000100", "scale": "5", "ma": "no", "datalen": "1500",
    })
    url = ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/"
           "CN_MarketData.getKLineData?" + q)
    raw = get(url).strip()
    if raw.startswith("var ") or not raw.startswith("["):
        raise ValueError("SINA_UNEXPECTED_DATA_FORMAT: " + raw[:80])
    data = json.loads(raw)
    if not isinstance(data, list) or not data:
        raise ValueError("SINA_EMPTY_BARS")
    rows = []
    for item in data:
        date_value = item.get("day") or item.get("date")
        if not date_value:
            raise ValueError("SINA_MISSING_DATE")
        stamp = datetime.strptime(date_value[:16], "%Y-%m-%d %H:%M").replace(tzinfo=CN)
        vol = float(item["volume"])
        if not math.isfinite(vol) or vol < 0:
            raise ValueError("SINA_INVALID_VOLUME")
        if stamp.strftime("%H:%M") in LABELS:
            rows.append((stamp, vol))
    if len(rows) != len({a for a, _ in rows}):
        raise ValueError("SINA_DUPLICATE_BARS")
    return sorted(rows), "Sina public 5-minute klines", None


def verify(rows, provider, lot_factor):
    from flow_locks.activity import relative_volume, LABELS
    raw = relative_volume(rows, ASOF, previous_sessions=HISTORY_DAYS, threshold=1.5)
    dates = {}
    for stamp, volume in rows:
        local = stamp.astimezone(CN)
        k = local.strftime("%Y-%m-%d")
        h = local.strftime("%H:%M")
        if h in LABELS and h <= CHECKPOINT:
            dates.setdefault(k, {})[h] = dates.setdefault(k, {}).get(h, 0) + volume
    today = ASOF.date().isoformat()
    actual_today = sum(dates.get(today, {}).values())
    # Explicitly label volume unit; on Sina detect shares vs lots against screenshot.
    if lot_factor is None:
        candidates = (1, 100)
        lot_factor = min(candidates, key=lambda x: abs(actual_today/x - EXPECTED_HANDS))
    hands_today = actual_today / lot_factor
    mismatch = abs(hands_today - EXPECTED_HANDS) / EXPECTED_HANDS
    if mismatch > .03:
        raise ValueError("USER_SCREENSHOT_CROSSCHECK_MISMATCH: source=" +
                         str(round(hands_today)) + ", screenshot=" + str(round(EXPECTED_HANDS)) +
                         ", relative_diff=" + str(round(mismatch,4)))
    prior = sorted(d for d in dates if d < today)[-HISTORY_DAYS:]
    expected_slots = [s for s in LABELS if s <= CHECKPOINT]
    details = []
    for d in prior:
        if set(expected_slots) - set(dates[d]):
            raise ValueError("HISTORY_MISSING_SLOTS: "+d)
        details.append({"date": d, "morning_hands": round(sum(dates[d][s] for s in expected_slots)/lot_factor)})
    mean_hands = sum(x["morning_hands"] for x in details) / len(details)
    ratio = EXPECTED_HANDS / mean_hands
    if abs(ratio - raw["same_time_volume_ratio"]) > .03:
        raise ValueError("RATIO_INTERNAL_CROSSCHECK_FAILED")
    return {
        "status": "VOLUME_LOCK_VERIFIED" if ratio >= 1.5 else "VOLUME_LOCK_FAILED",
        "snapshot": "2026-11-19 11:30 Asia/Shanghai",
        "symbol": SYMBOL,
        "provider": provider,
        "source_volume_unit_factor_to_hands": lot_factor,
        "screenshot_today_morning_hands": round(EXPECTED_HANDS),
        "provider_today_morning_hands": round(hands_today),
        "screenshot_provider_difference_fraction": round(mismatch, 5),
        "baseline_sessions": len(details),
        "baseline_prior_sessions": [details[0]["date"], details[-1]["date"]],
        "mean_prior_20_sessions_1130_hands": round(mean_hands),
        "same_time_relative_volume": round(ratio, 4),
        "threshold": 1.5,
        "volume_lock_pass": ratio >= 1.5,
        "proprietary_compass_3d_flow": "NOT_VERIFIED",
        "warning": "Historical snapshot only; not a live quote or a BUY signal",
        "per_day_morning_volume": details,
    }


def main():
    errors = []
    for provider in (eastmoney, sina):
        try:
            rows, name, factor = provider()
            result = verify(rows, name, factor)
            print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
            return 0
        except Exception as exc:
            errors.append({"provider": provider.__name__,
                           "error": type(exc).__name__ + ": " + str(exc)[:280]})
            print("PROVIDER_ERROR: " + json.dumps(errors[-1], ensure_ascii=False), flush=True)
    print(json.dumps({"status": "UNVERIFIED", "date": "2026-11-19",
                      "reason": "All sources failed strict 20-session or screenshot cross-check",
                      "provider_errors": errors}, ensure_ascii=False, indent=2))
    return 2


if __name__ == "__main__":
    sys.exit(main())
