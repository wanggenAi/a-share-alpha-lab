"""Check Eastmoney main-flow-only and daily close data for TCL 000100.

Third-party main flow is NOT the proprietary Compass main+hot-money model.
All date/price/turnover checks are explicit; output never authorizes a trade.
"""
from __future__ import annotations
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from .cli import funds, prices

TICKER = "000100"
TODAY = "2026-11-19"
SCREENSHOT_PRICE = 4.81
SCREENSHOT_TURNOVER = 858_000_000
SCREENSHOT_MAIN = -7_163_000

def run():
    out = {"symbol": TICKER, "snapshot": TODAY+" 11:30 Asia/Shanghai",
           "provider": "Eastmoney public estimated main-order flow",
           "not_equivalent_to_compass_3day": True, "no_trade_signal": True}
    try:
        pr = prices(TICKER, 50)
        past = [r for r in pr if r[0] < TODAY]
        out["ma20_before_today"] = round(sum(r[1] for r in past[-20:])/20, 4) if len(past)>=20 else None
        out["prev20_close_count"] = min(20, len(past))
        f = dict(funds(TICKER,101,30))
        out["fund_history_last_dates"] = list(f)[-6:]
        closed = [p for p in pr if p[0] < TODAY][-3:]
        if len(closed)==3 and all(x[0] in f for x in closed):
            summary = [{"date":d, "main_flow_yuan":round(f[d]), "turnover_yuan":round(amt)}
                       for d,close,vol,amt in closed]
            total=sum(x["turnover_yuan"] for x in summary)
            out["last_three_completed_sessions"] = {"dates":summary,
               "main_only_strength_pct":round(100*sum(x["main_flow_yuan"] for x in summary)/total,4),
               "positive_days":sum(x["main_flow_yuan"]>0 for x in summary)}
        else:
            out["closed_sessions_error"] = "MISSING_HISTORIC_MAIN_FLOW_OR_PRICE_DATES"
        current = next((p for p in pr if p[0]==TODAY), None)
        if current is None:
            out["today_status"] = "CURRENT_DAILY_BAR_MISSING"
        else:
            out["today_source_close"] = current[1]
            out["today_source_turnover"] = current[3]
            p_err=abs(current[1]-SCREENSHOT_PRICE)
            t_err=abs(current[3]-SCREENSHOT_TURNOVER)/SCREENSHOT_TURNOVER
            out["today_crosscheck"] = {"screenshot_close":SCREENSHOT_PRICE,
              "screenshot_turnover":SCREENSHOT_TURNOVER,
              "price_difference_yuan":round(p_err,4),
              "turnover_difference_fraction":round(t_err,5)}
            if p_err <= 0.03 and t_err <= 0.05 and TODAY in f:
                out["today_estimated_main_yuan"] = round(f[TODAY])
                out["today_vs_compass_main_difference_yuan"] = round(f[TODAY]-SCREENSHOT_MAIN)
                prior2 = [p for p in pr if p[0] < TODAY][-2:]
                if len(prior2)==2 and all(x[0] in f for x in prior2):
                    rows=[{"date":d,"main_yuan":round(f[d]),"turnover_yuan":round(a)} for d,c,v,a in prior2]
                    rows.append({"date":TODAY,"main_yuan":round(f[TODAY]),"turnover_yuan":round(current[3])})
                    out["rolling_3d_asof_1130_same_provider"] = {
                       "days": rows,
                       "main_only_pct":round(100*sum(r["main_yuan"] for r in rows) /
                                              sum(r["turnover_yuan"] for r in rows),4),
                       "positive_days":sum(r["main_yuan"]>0 for r in rows),
                       "warning":"Main funds ONLY. Not Compass main+hot-money, may differ by provider methodology."
                    }
            else:
                out["today_status"] = "FUNDS_NOT_VALIDATED_AGAINST_MIDDAY_SCREENSHOT"
        out["status"] = "PARTIAL_EASTMONEY_RESEARCH"
    except Exception as ex:
        out["status"] = "UNVERIFIED"
        out["error"] = type(ex).__name__+": "+str(ex)[:250]
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__ == "__main__":
    run()
