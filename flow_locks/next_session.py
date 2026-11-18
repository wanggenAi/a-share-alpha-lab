"""Create conservative next-session paper plan from verified post-close evidence."""
import argparse
import json
import math
import os
from pathlib import Path

def gate(stock, trading_date, capital=10000.0, max_risk=100.0):
    result={"symbol":stock.get("symbol","?"),"decision":"NO_TRADE",
            "buy_signal":False,"order_permitted":False}
    if stock.get("market_date")!=trading_date:
        result["reason"]="DATA_DATE_MISMATCH"
        return result
    if stock.get("status")=="DATA_BLOCKED":
        result["reason"]="PROVIDER_DATA_MISSING"
        return result
    if stock.get("status")!="RESEARCH_TRIPLE_PASS":
        result["reason"]="TRIPLE_LOCK_NOT_MET"
        return result
    if any(stock.get(k,{}).get("pass") is not True
           for k in ("trend_lock","main_funds_lock","activity_lock")):
        result["reason"]="LOCK_EVIDENCE_MISSING"
        return result
    if stock.get("chase_risk_flag") is not False:
        result["reason"]="CHASE_RISK"
        return result
    try:
        close,high,low=[float(stock[k]) for k in ("close","high","low")]
        if not all(map(math.isfinite,[close,high,low])) or low<=0 or high<close or close<low:
            raise ValueError("bad price")
        if capital<=0 or max_risk<=0: raise ValueError("bad budget")
        entry=round(high+0.01,2)
        stop=round(low-0.01,2)
        r=round(entry-stop,2)
        if r<=0 or r/entry>0.06:
            result["reason"]="STOP_DISTANCE_TOO_WIDE"
            return result
        shares=min(int(capital/entry/100),int(max_risk/r/100))*100
        if shares<100:
            result["reason"]="RISK_BUDGET_BELOW_ONE_LOT"
            return result
    except (TypeError,ValueError,KeyError,OverflowError):
        result["reason"]="INVALID_PRICE_OR_BUDGET"
        return result
    result.update(decision="WATCH_PENDING_VALUE_AND_TOMORROW",
                  reason="Must verify financials, valuation, fresh next-session money flow and volume",
                  hypothetical_entry_yuan=entry,hypothetical_stop_yuan=stop,
                  hypothetical_2r_yuan=round(entry+2*r,2),
                  paper_shares=shares,planned_risk_yuan=round(r*shares,2),
                  fundamental_verified=False,next_session_confirmed=False)
    return result

def compile_report(data,capital=10000.0,max_risk=100.0):
    date=data.get("market_date_cn")
    stocks=data.get("stocks",[])
    if not isinstance(date,str) or len(date)!=10 or not isinstance(stocks,list):
        return {"status":"DATA_BLOCKED","buy_signal":False,
                "decisions":[],"watch":[],"reason":"MISSING_POST_CLOSE_EVIDENCE"}
    decisions=[gate(s,date,capital,max_risk) for s in stocks]
    watches=[x for x in decisions if x["decision"].startswith("WATCH")]
    return {"status":"WATCHES_REQUIRE_MANUAL_REVIEW" if watches else "NO_VERIFIED_ENTRY",
            "market_date":date,"source_status":data.get("status"),
            "total":len(stocks),"data_missing":sum(s.get("status")=="DATA_BLOCKED" for s in stocks),
            "buy_signal":False,"automatic_order":False,
            "watch":watches,"decisions":decisions,
            "caveat":"Hypothetical previous-day break, stop and 2R are not verified levels. A-share T+1, gaps and price limits apply."}

def display(out):
    lines=["## 明日观察和否决名单（不自动交易）","",
           "交易日："+str(out.get("market_date","未知")),
           "状态："+str(out.get("status")),"",
           "| 股票 | 结果 | 原因 | 假设触发价 | 参考止损 | 纸面股数 |",
           "|---|---|---|---:|---:|---:|"]
    for d in out.get("decisions",[]):
        cols=[d.get("symbol"),d.get("decision"),d.get("reason"),
              d.get("hypothetical_entry_yuan","—"),
              d.get("hypothetical_stop_yuan","—"),d.get("paper_shares","—")]
        lines.append("| "+" | ".join(str(x).replace("|","/") for x in cols)+" |")
    lines += ["",f"数据完整度：{out.get('total',0)-out.get('data_missing',0)}/{out.get('total',0)}。",
              "**未经基本面、估值及次日盘中确认，一律不生成买入信号。**",""]
    return "\n".join(lines)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="post-close.json")
    p.add_argument("--out",default="next-session.json")
    p.add_argument("--capital",type=float,default=10000)
    p.add_argument("--risk",type=float,default=100)
    a=p.parse_args()
    src=Path(a.input)
    data=json.loads(src.read_text(encoding="utf-8")) if src.exists() else {}
    res=compile_report(data,capital=a.capital,max_risk=a.risk)
    Path(a.out).write_text(json.dumps(res,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    message=display(res);print(message)
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as f:f.write(message+"\n")
    return 0

if __name__=="__main__":raise SystemExit(main())
