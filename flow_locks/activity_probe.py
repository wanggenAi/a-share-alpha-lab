"""Check 5-minute source connectivity independently of a buy signal."""
import argparse
from datetime import datetime, timezone, timedelta
import json
from .activity import five_minute_volume, relative_volume

def check(symbol):
    out={"symbol":symbol,"status":"UNAVAILABLE","research_only":True}
    try:
        rows=five_minute_volume(symbol)
        latest=rows[-1][0]
        out.update(rows=len(rows),session_count=len(set(r[0].date() for r in rows)),
                   latest_candle_cn=latest.isoformat(timespec="minutes"))
        # Historical replay at last observed 5m close plus 2 minutes.
        # The replay timestamp is not a live market quote.
        replay_at=latest+timedelta(minutes=2)
        out["historical_replay"]=relative_volume(rows,replay_at)
        out["status"]="HISTORICAL_REPLAY_AVAILABLE"
    except Exception as exc:
        out["reason"]=f"{type(exc).__name__}: {str(exc)[:160]}"
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbols",nargs="+",default=["000100"])
    a=p.parse_args()
    print(json.dumps({"checked_at_utc":datetime.now(timezone.utc).isoformat(),
                      "results":[check(c) for c in a.symbols]},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
