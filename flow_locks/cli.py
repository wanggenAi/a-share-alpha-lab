"""Research-only A-share capital flow probe. Not institutional account data or trade advice."""
import argparse
import json
import math
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

CN=ZoneInfo("Asia/Shanghai")
BASE="https://push2.eastmoney.com/api/qt/stock/"
HIST="https://push2his.eastmoney.com/api/qt/stock/"

def market_id(code):
    if not re.fullmatch(r"\d{6}",code): raise ValueError("ticker must have six digits")
    if code.startswith(("6","9")): return "1."+code
    if code.startswith(("0","3")): return "0."+code
    raise ValueError("unsupported A-share ticker")

def query(path, params):
    url=(HIST if path=="kline/get" else BASE)+path+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0",
        "Referer":"https://data.eastmoney.com/"})
    with urllib.request.urlopen(req,timeout=10) as response:
        payload=json.loads(response.read(2000000).decode("utf-8-sig"))
    if payload.get("rc")!=0 or not isinstance(payload.get("data"),dict):
        raise ValueError("provider response invalid")
    return payload["data"]

def funds(code,klt,limit):
    obj=query("fflow/kline/get",{
        "secid":market_id(code),"klt":klt,"lmt":limit,
        "fields1":"f1,f2,f3,f7","fields2":"f51,f52,f53,f54,f55,f56"})
    rows=obj.get("klines")
    if not rows: raise ValueError("no fund rows")
    out=[]
    for line in rows:
        cells=line.split(",")
        stamp,amount=cells[0],float(cells[1])
        if not math.isfinite(amount): raise ValueError("bad fund amount")
        out.append((stamp,amount))
    if [r[0] for r in out]!=sorted(r[0] for r in out):
        raise ValueError("funds date order invalid")
    return out

def prices(code,limit=80):
    obj=query("kline/get",{
        "secid":market_id(code),"klt":101,"fqt":0,"end":"20500101",
        "lmt":limit,"fields1":"f1,f2,f3,f4,f5,f6",
        "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"})
    lines=obj.get("klines")
    if not lines: raise ValueError("no daily prices")
    result=[]
    for line in lines:
        c=line.split(",")
        if len(c)<7: raise ValueError("invalid daily row")
        item=(c[0],float(c[2]),float(c[5]),float(c[6]))
        if not all(map(math.isfinite,item[1:])) or item[1]<=0 or item[3]<0:
            raise ValueError("invalid daily amount")
        result.append(item)
    if [r[0] for r in result]!=sorted(r[0] for r in result):
        raise ValueError("price date order invalid")
    return result

def three_day_strength(daily_funds, daily_prices, today):
    f={d:v for d,v in daily_funds if d<today}
    p=[row for row in daily_prices if row[0]<today]
    if len(p)<3: raise ValueError("insufficient closed sessions")
    recent=p[-3:]
    if any(row[0] not in f or row[3]<=0 for row in recent):
        raise ValueError("unmatched series quote_dates="+str([r[0] for r in recent])+" fund_dates="+str(sorted(f)[-6:]))
    net=sum(f[row[0]] for row in recent)
    total=sum(row[3] for row in recent)
    return {"dates":[r[0] for r in recent],
            "main_net_yuan":round(net,2),
            "turnover_yuan":round(total,2),
            "main_strength_pct":round(100*net/total,4),
            "positive_days":sum(f[r[0]]>0 for r in recent)}

def is_trading(now):
    n=now.astimezone(CN)
    t=n.time()
    return n.weekday()<5 and (time(9,30)<=t<=time(11,30) or time(13)<=t<=time(15))

def inspect(code,now,stale_after=10):
    n=now.astimezone(CN)
    today=n.date().isoformat()
    out={"symbol":code,"checked_at_cn":n.isoformat(timespec="seconds"),
         "provider":"Eastmoney public page API; estimated funds; unofficial",
         "status":"DATA_BLOCKED","buy_signal":False,
         "limitations":["not Compass three-lock or true institution identity",
                        "no validated same-minute relative volume",
                        "no price execution or complete valuation checks"]}
    try:
        historical=funds(code,101,12)
        minute=funds(code,1,300)
        daily=prices(code)
        out["completed_3d"]=three_day_strength(historical,daily,today)
        if not is_trading(now):
            out["status"]="MARKET_CLOSED_OR_BREAK"
            return out
        latest=datetime.strptime(minute[-1][0],"%Y-%m-%d %H:%M").replace(tzinfo=CN)
        age=(n-latest).total_seconds()/60
        out.update(latest_fund_minute=latest.isoformat(timespec="minutes"),
                   data_age_minutes=round(age,2))
        if latest.date().isoformat()!=today or age< -2 or age>stale_after:
            out["status"]="STALE"
            return out
        if daily[-1][0]!=today or daily[-1][3]<=0 or len(daily)<20:
            out["status"]="STALE_OR_INSUFFICIENT_QUOTE"
            return out
        close=[r[1] for r in daily]
        ma5=sum(close[-5:])/5;ma10=sum(close[-10:])/10;ma20=sum(close[-20:])/20
        current=100*minute[-1][1]/daily[-1][3]
        trend=close[-1]>=ma20 and ma5>=ma10
        prior=out["completed_3d"]
        main=(prior["main_strength_pct"]>=3 and prior["positive_days"]>=2 and current>0)
        out.update(
            price=close[-1],today_main_estimate_yuan=minute[-1][1],
            today_turnover_yuan=daily[-1][3],
            today_main_strength_pct=round(current,4),
            trend_lock={"pass":trend,"ma5":round(ma5,3),"ma10":round(ma10,3),"ma20":round(ma20,3)},
            main_funds_lock={"pass":main,"threshold_pct_experimental":3.0,
                             "note":"main only, not main+hot-money"},
            activity_lock={"pass":None,"reason":"same-minute historical turnover missing"},
            status="RESEARCH_WATCH" if trend and main else "WAIT",
            warning="NO BUY: activity lock, risk and fundamental valuation are not verified"
        )
    except Exception as ex:
        out.update(status="DATA_BLOCKED",error=f"{type(ex).__name__}: {str(ex)[:150]}")
    return out

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--symbols",nargs="+",default=["000100","600206","603993"])
    parser.add_argument("--json-out",default="")
    args=parser.parse_args()
    now=datetime.now(timezone.utc)
    result={"generated_at_utc":now.isoformat(),"data":[inspect(c,now) for c in args.symbols]}
    content=json.dumps(result,indent=2,ensure_ascii=False)
    if args.json_out:
        with open(args.json_out,"w",encoding="utf-8") as f: f.write(content+"\n")
    print(content)
    return 0 if all(row["status"]!="DATA_BLOCKED" for row in result["data"]) else 2

if __name__=="__main__": sys.exit(main())
