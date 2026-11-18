"""Render observed flow snapshot as a readable GitHub Actions summary."""
import json
import os
import sys
from pathlib import Path

def render(path):
    p=Path(path)
    if not p.exists(): return "## 资金锁探针：未返回数据\n\n行情接口未生成文件，请查看任务日志。\n"
    data=json.loads(p.read_text(encoding="utf-8"))
    lines=["## 资金锁研究快照（非买卖信号）","",
           "生成时间 UTC: "+str(data.get("generated_at_utc","unknown")),"",
           "| 代码 | 价格 | 3日主力资金强度 | 今日盘中强度 | 趋势 | 资金 | 活跃 | 状态 |",
           "|---|---:|---:|---:|---|---|---|---|"]
    for x in data.get("data",[]):
        tr=x.get("trend_lock",{})
        fl=x.get("main_funds_lock",{})
        act=x.get("activity_lock",{})
        def flag(obj):
            v=obj.get("pass")
            return "通过" if v is True else "未通过" if v is False else "未知"
        cells=[x.get("symbol","?"),
               x.get("price","—"),
               str(x.get("completed_3d",{}).get("main_strength_pct","—"))+"%",
               str(x.get("today_main_strength_pct","—"))+"%",
               flag(tr),flag(fl),flag(act),str(x.get("status","UNKNOWN"))]
        lines.append("| "+" | ".join(str(c).replace("|","/") for c in cells)+" |")
    lines.extend(["","数据：东方财富公开行情页接口估算；不代表机构真实买卖。",
                  "缺少同分钟量比与风险验证，不能视为开仓指令。"])
    return "\n".join(lines)+"\n"

if __name__=="__main__":
    summary=render(sys.argv[1] if len(sys.argv)>1 else "flow-snapshot.json")
    dest=os.environ.get("GITHUB_STEP_SUMMARY")
    if dest:
        with open(dest,"a",encoding="utf-8") as f:f.write(summary)
    print(summary)
