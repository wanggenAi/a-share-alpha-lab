"""Post-close markdown report for GitHub Actions (research only)."""
import json
import os
import sys
from pathlib import Path

def render(path):
    if not Path(path).exists():
        return "## 明日候选盘后报告\n\n数据读取失败，禁止给出开仓结论。\n"
    x=json.loads(Path(path).read_text(encoding="utf-8"))
    lines=["## 收盘后的下一交易日研究候选（非买单）","",
           "交易日："+str(x.get("market_date_cn","?")),
           "状态："+str(x.get("status","UNKNOWN")),
           "",
           "| 股票 | 收盘价 | 3日主力强度 | 今日主力强度 | 同时段量比 | 趋势 | 资金 | 活跃 | 状态 |",
           "|---|---:|---:|---:|---:|---|---|---|---|"]
    for s in x.get("stocks",[]):
        def check(obj):
            v=(obj or {}).get("pass")
            return "通过" if v is True else "不通过" if v is False else "未知"
        h=s.get("historical_3d") or {}
        a=s.get("activity_lock") or {}
        cells=[s.get("symbol"),s.get("close","—"),h.get("pct","—"),
               s.get("estimated_today_pct","—"),a.get("same_time_volume_ratio","—"),
               check(s.get("trend_lock")),check(s.get("main_funds_lock")),check(a),s.get("status")]
        lines.append("| "+" | ".join(map(str,cells))+" |")
    lines.extend(["","优先进一步人工研究："+", ".join(x.get("research_priority",[])),
                  "","**缺少财报/估值/价位/交易状态审核，任何结果均不是直接买入指令。**"])
    return "\n".join(lines)+"\n"

if __name__=="__main__":
    text=render(sys.argv[1] if len(sys.argv)>1 else "post-close.json")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf-8") as f:f.write(text)
    print(text)
