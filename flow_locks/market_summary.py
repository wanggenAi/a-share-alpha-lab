"""Human readable Actions output for complete/partial market discovery."""
import json
import os
import sys
from pathlib import Path

def fmt(x):
    if x is None:return "—"
    return str(x).replace("|","/").replace("\n"," ")

def render(file):
    p=Path(file)
    if not p.is_file():
        return "## A股全市场资金扫描\n\n未能生成数据文件，详情见运行日志。\n"
    x=json.loads(p.read_text(encoding="utf-8"))
    lines=["## A股全市场资金候选扫描","",
           f"运行状态：**{fmt(x.get('status'))}**",
           f"快照 UTC：{fmt(x.get('generated_at_utc'))}",
           f"市场返回数量：{fmt(x.get('reported_market_total'))}；已读取页：{fmt(x.get('retrieved_pages'))} / {fmt(x.get('expected_pages'))}",
           f"主板记录：{fmt(x.get('main_board_quotes'))}；资金占比可交叉验证：{fmt(x.get('flow_ratio_cross_checked'))}",
           ""]
    if not x.get("all_pages_complete"):
        lines += ["**数据不完整：候选榜单被禁止输出，不得据此交易。**","",
                  f"错误：{fmt(x.get('errors') or x.get('error'))}",""]
    else:
        lines += ["**仅是资金筛查候选，不是买入信号，也未完成价值/估值验证。**","",
                  "| 排名 | 股票 | 价格 | 当日主力估算强度 | 成交额(亿元) | 报价时间 |",
                  "|---:|---|---:|---:|---:|---|"]
        for i,c in enumerate(x.get("candidates",[])[:20],start=1):
            lines.append("| "+" | ".join(map(fmt,[
                i,c["symbol"]+" "+c["name"],c["price"],
                str(c["computed_main_ratio_pct"])+"%",
                round(c["turnover_yuan"]/1e8,2),c.get("quote_at_cn") or "未返回"
            ]))+" |")
        lines += ["","### 三日深度核查（只用于研究）","",
                  "| 股票 | 3日净流入强度 | 今日资金 | 趋势锁 | 活跃锁 | 状态 |",
                  "|---|---:|---:|---|---|---|"]
        for c in x.get("deep_checked",[]):
            r=c["result"]
            three=r.get("completed_3d") or {}
            t=r.get("trend_lock") or {}
            a=r.get("activity_lock") or {}
            lines.append("| "+" | ".join(map(fmt,[
                c["symbol"]+" "+c["name"],
                three.get("main_strength_pct","—"),
                r.get("today_main_strength_pct","—"),
                t.get("pass","未知"),
                a.get("pass","未知"),
                r.get("status","UNKNOWN")
            ]))+" |")
    lines += ["","数据为供应商估算，不代表机构真实成交；不自动下单。缺失数据、封锁或延迟必须明确标出。"]
    return "\n".join(lines)+"\n"

if __name__=="__main__":
    text=render(sys.argv[1] if len(sys.argv)>1 else "market-snapshot.json")
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write(text)
    print(text)
