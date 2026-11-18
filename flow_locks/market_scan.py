"""Full-market candidate discovery; a snapshot is not proof of a tradable buy signal.

Uses an undocumented public quote page endpoint. Provider order flow is an estimate,
not verified institutional trades. Missing pages, units or dates fail closed.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import urllib.error
import http.client
from zoneinfo import ZoneInfo

from .cli import inspect, CN, is_trading

API = "https://push2.eastmoney.com/api/qt/clist/get"
MARKETS = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
FIELDS = "f12,f13,f14,f2,f3,f6,f8,f62,f184,f124"
# Conservative page size; some provider deployments cap pages at 100 records.
PAGE_SIZE = 100
MAX_TOTAL = 10000

def _number(v):
    if isinstance(v, bool) or v is None or v == "-": return None
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def is_main_board(code, market):
    if not re.fullmatch(r"\d{6}", code): return False
    if market == 1:
        return code.startswith(("600", "601", "603", "605"))
    if market == 0:
        return code.startswith(("000", "001", "002", "003"))
    return False

def parse_market_record(raw):
    if not isinstance(raw, dict): return None
    code = str(raw.get("f12") or "")
    name = str(raw.get("f14") or "").strip()
    market = _number(raw.get("f13"))
    if not re.fullmatch(r"\d{6}", code) or not name or market is None:
        return None
    price = _number(raw.get("f2"))
    change = _number(raw.get("f3"))
    turnover = _number(raw.get("f6"))
    net = _number(raw.get("f62"))
    provider_ratio = _number(raw.get("f184"))
    stamp = _number(raw.get("f124"))
    quote_at = None
    if stamp is not None and 1600000000 <= stamp <= 2050000000:
        quote_at = datetime.fromtimestamp(int(stamp), CN).isoformat(timespec="seconds")
    if price is None or price <= 0 or turnover is None or turnover <= 0:
        return None
    # f62 and f6 are both advertised in yuan. Do not silently change units.
    calc = net / turnover * 100 if net is not None else None
    cross_checked = (
        calc is not None and provider_ratio is not None
        and abs(calc - provider_ratio) <= max(0.35, abs(provider_ratio) * 0.04)
    )
    risk_name = "ST" in name.upper() or "退" in name or name.startswith(("N", "C"))
    return {
        "symbol": code, "name": name, "exchange_market_id": int(market),
        "main_board": is_main_board(code, int(market)),
        "risk_name_flag": risk_name, "price": price,
        "change_pct": change, "turnover_yuan": turnover,
        "main_net_yuan": net, "provider_main_ratio_pct": provider_ratio,
        "computed_main_ratio_pct": round(calc, 4) if calc is not None else None,
        "flow_ratio_verified": cross_checked, "quote_at_cn": quote_at,
        "quote_in_trading_session": bool(quote_at and is_trading(datetime.fromisoformat(quote_at))),
        "extreme_estimate_flag": bool(calc is not None and abs(calc) >= 30),
        "sharp_rise_flag": bool(change is not None and change > 5),
    }

def fetch_page(page, page_size=PAGE_SIZE):
    params = {
        "pn": page, "pz": page_size, "po": 1, "np": 1,
        "fid": "f6", "fs": MARKETS, "fields": FIELDS,
        "fltt": 2, "invt": 2, "ut": "bd1d9ddb04089700cf9c27f6f7426281",
    }
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"User-Agent":"Mozilla/5.0", "Referer":"https://data.eastmoney.com/"}
    )
    # Network-source retry only, never fill in fabricated pages.
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                blob = resp.read(1_500_000).decode("utf-8-sig")
            break
        except (urllib.error.URLError, http.client.RemoteDisconnected,
                TimeoutError, ConnectionError, OSError) as exc:
            if isinstance(exc, urllib.error.HTTPError) and exc.code not in (429,500,502,503,504):
                raise
            if attempt == 2: raise
            time.sleep(1.0 + attempt*2.5)
    result = json.loads(blob)
    if not isinstance(result, dict) or result.get("rc") != 0 or not isinstance(result.get("data"), dict):
        raise ValueError("market list request failed")
    data = result["data"]
    raw_rows = data.get("diff")
    if isinstance(raw_rows, dict):
        rows = list(raw_rows.values())
    elif isinstance(raw_rows, list):
        rows = raw_rows
    else:
        rows = []
    total = data.get("total")
    if not isinstance(total, int) or not (1 <= total <= MAX_TOTAL):
        raise ValueError("invalid market universe total")
    return total, rows

def assemble_pages(pages, total, page_size=PAGE_SIZE):
    """Input contains page_number -> raw provider rows. No missing/duplicate pages."""
    if not (1 <= total <= MAX_TOTAL): raise ValueError("invalid total")
    expected = (total + page_size - 1)//page_size
    if set(pages) != set(range(1, expected + 1)):
        raise ValueError("incomplete or extra market pages")
    raw = []
    seen = set()
    for page in range(1,expected+1):
        part = pages[page]
        need = min(page_size,total-(page-1)*page_size)
        if len(part)!=need:
            raise ValueError(f"page {page} has {len(part)} records, expected {need}")
        for entry in part:
            sym=str(entry.get("f12") if isinstance(entry,dict) else "")
            mk=str(entry.get("f13") if isinstance(entry,dict) else "")
            key=(mk,sym)
            if key in seen: raise ValueError("duplicate market listing")
            seen.add(key);raw.append(entry)
    if len(raw)!=total: raise ValueError("market row total mismatch")
    return raw

def rank_candidates(rows, *, top=50, min_turnover=50_000_000):
    """Never use net ratio without checking the independent provider percentage."""
    eligible=[]
    for item in rows:
        p=parse_market_record(item)
        if (p and p["main_board"] and not p["risk_name_flag"]
            and p["flow_ratio_verified"] and p["turnover_yuan"] >= min_turnover
            and p["computed_main_ratio_pct"] >= 3.0
            and p["price"] > 0):
            eligible.append(p)
    eligible.sort(key=lambda r:(-r["computed_main_ratio_pct"], -r["turnover_yuan"],r["symbol"]))
    return eligible[:top]

def collect(max_pages=None, pause=0.18):
    # first fetch determines reported market universe
    total, first = fetch_page(1)
    expected = (total + PAGE_SIZE - 1)//PAGE_SIZE
    pages={1:first}
    limit = expected if max_pages is None else min(max_pages,expected)
    errors=[]
    for p in range(2, limit+1):
        if pause: time.sleep(pause)
        try:
            new_total, rows=fetch_page(p)
            if new_total!=total: raise ValueError("universe total changed mid-scan")
            pages[p]=rows
        except Exception as exc:
            errors.append(f"page {p}: {type(exc).__name__}: {str(exc)[:120]}")
            break
    if len(pages)!=expected or errors:
        return {
            "status":"PARTIAL_DO_NOT_RANK",
            "reported_market_total":total, "expected_pages":expected,
            "retrieved_pages":len(pages), "errors":errors,
            "candidates":[], "all_pages_complete":False
        }
    raw=assemble_pages(pages,total)
    parsed=[parse_market_record(x) for x in raw]
    return {
        "status":"COMPLETE_SNAPSHOT_UNVERIFIED_FRESHNESS",
        "reported_market_total":total, "expected_pages":expected,
        "retrieved_pages":len(pages), "parsed_quotes":sum(p is not None for p in parsed),
        "main_board_quotes":sum(bool(p and p["main_board"]) for p in parsed),
        "flow_ratio_cross_checked":sum(bool(p and p["flow_ratio_verified"]) for p in parsed),
        "with_quote_timestamp":sum(bool(p and p["quote_at_cn"]) for p in parsed),
        "all_pages_complete":True,
        "candidates":rank_candidates(raw), "errors":[]
    }

def run_market_scan(*, max_pages=None, deep=5, pause=0.18):
    now=datetime.now(timezone.utc)
    out={
        "generated_at_utc":now.isoformat(timespec="seconds"),
        "method":"Snapshot ranks by f62/f6 x100, cross-check with f184; main-board only",
        "notice":"Estimated provider flows; NOT real institution trades, NOT a BUY signal.",
        "status":"DATA_BLOCKED", "buy_signal":False,
    }
    try:
        out.update(collect(max_pages=max_pages,pause=pause))
        elapsed=(datetime.now(timezone.utc)-now).total_seconds()
        out["scan_duration_seconds"]=round(elapsed,1)
        out["snapshot_atomicity"]="MULTI_MINUTE_NONATOMIC" if elapsed>90 else "NOT_ATOMIC"
        if not out["all_pages_complete"]: return out
        selected=out["candidates"][:max(0,deep)]
        out["deep_checked"]=[]
        for i, candidate in enumerate(selected):
            if pause: time.sleep(pause)
            result=inspect(candidate["symbol"],now)
            out["deep_checked"].append({
                "symbol":candidate["symbol"],"name":candidate["name"],
                "rank":i+1, "result":result
            })
        out["market_in_continuous_session_at_start"]=is_trading(now)
        out["status"]="RESEARCH_SNAPSHOT" if is_trading(now) else "MARKET_BREAK_OR_CLOSED_SNAPSHOT"
        return out
    except Exception as ex:
        out.update(status="DATA_BLOCKED",error=f"{type(ex).__name__}: {str(ex)[:180]}",
                   candidates=[], deep_checked=[], buy_signal=False)
        return out

def main():
    p=argparse.ArgumentParser(description="A-share full universe estimated flow scan; research only")
    p.add_argument("--max-pages",type=int,default=None)
    p.add_argument("--deep",type=int,default=5)
    p.add_argument("--page-delay",type=float,default=0.18)
    p.add_argument("--out",default="flow-market-scan.json")
    a=p.parse_args()
    if a.max_pages is not None and not (1<=a.max_pages<=100):
        p.error("max-pages must be 1..100")
    if not 0<=a.deep<=20: p.error("deep must be 0..20")
    if not 0<=a.page_delay<=3: p.error("page-delay must be 0..3")
    result=run_market_scan(max_pages=a.max_pages,deep=a.deep,pause=a.page_delay)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    summary={k:v for k,v in result.items() if k not in ("candidates","deep_checked")}
    summary["top10"]=[{"code":x["symbol"],"name":x["name"],"estimated_pct":x["computed_main_ratio_pct"]}
                     for x in result.get("candidates",[])[:10]]
    summary["deep_checked"]=[{"code":x["symbol"],"status":x["result"]["status"]}
                             for x in result.get("deep_checked",[])]
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    return 0 if result["status"] in ("RESEARCH_SNAPSHOT","MARKET_BREAK_OR_CLOSED_SNAPSHOT") else 2

if __name__=="__main__":
    raise SystemExit(main())
