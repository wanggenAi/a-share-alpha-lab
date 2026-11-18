"""Post-close multi-stock research, with strict as-of guards. No buy order signal."""
from __future__ import annotations
import argparse
from datetime import datetime, time, timedelta, timezone
from pathlib import Path
import json
import math
import time as time_module
from .cli import CN, query, market_id, funds
from .activity import five_minute_volume, relative_volume

DEFAULT_CODES=[
    "000100", # TCL technology
    "600206", # GRINM materials
    "002222", # CASTECH
    "000333", # Midea
    "600584", # JCET
    "002463", # WUS PCB
    "603209", # Xingtong
    "600036", # CMB
    "603993", # CMOC
]

def daily_bars(code, limit=90):
    res=query("kline/get",{
        "secid":market_id(code),"klt":101,"fqt":0,"end":"20500101",
        "lmt":limit,"fields1":"f1,f2,f3,f4,f5,f6",
        "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    })
    lines=res.get("klines")
    if not isinstance(lines,list) or len(lines)<25:
        raise ValueError("insufficient daily price history")
    rows=[]
    for line in lines:
        c=str(line).split(",")
        if len(c)<7: raise ValueError("malformed daily bar")
        day=c[0]
        # Eastmoney kline: date, open, close, high, low, volume lots, amount yuan.
        values=list(map(float,[c[1],c[2],c[3],c[4],c[5],c[6]]))
        op,cl,hi,lo,vol,amt=values
        if (not all(math.isfinite(v) for v in values)
            or min(op,cl,hi,lo)<=0 or lo>min(op,cl) or hi<max(op,cl)
            or vol<0 or amt<=0):
            raise ValueError("invalid daily bar fields")
        rows.append({"date":day,"open":op,"close":cl,"high":hi,"low":lo,
                     "volume_lots":vol,"turnover_yuan":amt})
    if len({x["date"] for x in rows})!=len(rows) or rows!=sorted(rows,key=lambda x:x["date"]):
        raise ValueError("duplicate/out-of-order daily dates")
    return rows

def three_complete(daily_funds, daily_prices, close_date):
    fund_map=dict(daily_funds)
    p=[x for x in daily_prices if x["date"]<=close_date]
    if len(p)<3 or p[-1]["date"]!=close_date:
        raise ValueError("latest price date does not match close date")
    last=p[-3:]
    if any(x["date"] not in fund_map for x in last):
        raise ValueError("missing exact-date daily main-flow records")
    total=sum(x["turnover_yuan"] for x in last)
    net=sum(fund_map[x["date"]] for x in last)
    if total<=0: raise ValueError("zero turnover")
    return {"dates":[x["date"] for x in last],
            "net_yuan":round(net,2),
            "total_turnover_yuan":round(total,2),
            "pct":round(100*net/total,4),
            "positive_days":sum(fund_map[x["date"]]>0 for x in last),
            "daily_net_yuan":{x["date"]:round(fund_map[x["date"]],2) for x in last}}

def assess_close(code, *, now, close_date):
    out={"symbol":code,"market_date":close_date,
         "source":"Eastmoney public estimate; not actual institution ownership",
         "status":"DATA_BLOCKED","buy_signal":False}
    try:
        prices=daily_bars(code)
        last=prices[-1]
        if last["date"]!=close_date:
            raise ValueError(f"stale quote date {last['date']}")
        f=funds(code,101,15)
        strength=three_complete(f,prices,close_date)
        current_net=dict(f)[close_date]
        closes=[x["close"] for x in prices]
        ma5=sum(closes[-5:])/5
        ma10=sum(closes[-10:])/10
        ma20=sum(closes[-20:])/20
        # No reliance on single intraday signal for tomorrow's order.
        trend=(last["close"]>=ma20 and ma5>=ma10)
        fund_ok=strength["pct"]>=3 and strength["positive_days"]>=2 and current_net>0
        vol=relative_volume(
            five_minute_volume(code),
            datetime.fromisoformat(close_date+"T15:02:00").replace(tzinfo=CN),
            stale_after=12
        )
        if vol["comparison_end_cn"][:10]!=close_date or not vol["comparison_end_cn"].endswith("15:00+08:00"):
            raise ValueError("incomplete closing 5m volume candle")
        change=100*(last["close"]/prices[-2]["close"]-1)
        out.update(
            status="RESEARCH_TRIPLE_PASS" if trend and fund_ok and vol["pass"] else "WATCH_OR_REJECT",
            close=last["close"],open=last["open"],high=last["high"],low=last["low"],
            change_pct=round(change,3),turnover_yuan=last["turnover_yuan"],
            estimated_today_net_yuan=round(current_net,2),
            estimated_today_pct=round(100*current_net/last["turnover_yuan"],4),
            historical_3d=strength,
            trend_lock={"pass":trend,"ma5":round(ma5,4),"ma10":round(ma10,4),"ma20":round(ma20,4)},
            main_funds_lock={"pass":fund_ok,"experimental_threshold":3.0,"date":close_date},
            activity_lock=vol,
            chase_risk_flag=change>5,
            review_required=["fundamentals and valuation verified as-of published date",
                             "today full stop/limit/suspension status",
                             "next session entry price and exit risk/reward",
                             "tomorrow 09:30+ volume/flow confirmation"],
            buy_signal=False
        )
    except Exception as ex:
        out.update(status="DATA_BLOCKED",error=f"{type(ex).__name__}: {str(ex)[:160]}")
    return out

def run(codes,*, now=None):
    now=now or datetime.now(timezone.utc)
    cn=now.astimezone(CN)
    out={"generated_utc":now.isoformat(),"market_date_cn":cn.date().isoformat(),
         "research_only":True,"buy_signal":False,"status":"DATA_BLOCKED",
         "description":"Post-close data must reflect today, not morning snapshots."}
    if cn.time()<time(15,10) or cn.weekday()>4:
        out["error"]="post-close report only permitted after 15:10 on a weekday"
        return out
    out["stocks"]=[]
    for idx, code in enumerate(codes):
        if idx: time_module.sleep(1.0)
        out["stocks"].append(assess_close(code,now=now,close_date=cn.date().isoformat()))
    good=[x for x in out["stocks"] if x["status"]=="RESEARCH_TRIPLE_PASS" and not x.get("chase_risk_flag")]
    good.sort(key=lambda x:(-x["historical_3d"]["pct"],-x["turnover_yuan"]))
    out["research_priority"]=[x["symbol"] for x in good]
    out["passed_all_three_no_chase"]=len(good)
    out["blocked"]=sum(x["status"]=="DATA_BLOCKED" for x in out["stocks"])
    out["status"]="PARTIAL_OR_BLOCKED" if out["blocked"] else "COMPLETE_RESEARCH_ONLY"
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--symbols",nargs="+",default=DEFAULT_CODES)
    p.add_argument("--out",default="post-close.json")
    a=p.parse_args()
    result=run(a.symbols)
    Path(a.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    brief=[{"symbol":x["symbol"],"status":x["status"],"close":x.get("close"),
            "estimated_today_pct":x.get("estimated_today_pct"),
            "three_pct":x.get("historical_3d",{}).get("pct"),
            "relative_volume":x.get("activity_lock",{}).get("same_time_volume_ratio"),
            "error":x.get("error")} for x in result.get("stocks",[])]
    print(json.dumps({"status":result["status"],
                      "market_date":result["market_date_cn"],
                      "research_priority":result.get("research_priority",[]),
                      "blocked":result.get("blocked"),
                      "stocks":brief},ensure_ascii=False,indent=2))
    return 0 if result["status"]=="COMPLETE_RESEARCH_ONLY" else 2

if __name__=="__main__":
    raise SystemExit(main())
