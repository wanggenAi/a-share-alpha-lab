"""Static offline Chinese dashboard. All text is escaped, no external assets."""
from __future__ import annotations

from html import escape


def safe(value: object) -> str:
    return escape("—" if value is None else str(value), quote=True)


STATE_NAMES = {
    "WATCH_SIGNAL": "技术形态待研究",
    "WAIT_PRICE": "等待价格确认",
    "DORMANT_NO_CURRENT_SETUP": "形态暂不满足，保留跟踪",
    "BLOCKED_MISSING_OR_UNSAFE_DATA": "数据不足，暂缓判断",
    "REVIEW_DATA_MISSING": "缺少价格，暂缓判断",
    "REVIEW_HOLDING_WITH_TECHNICAL_SETUP": "持仓：形态待复核",
    "REVIEW_HOLDING_AWAITING_CONFIRMATION": "持仓：等待确认",
    "REVIEW_HOLDING_NO_CURRENT_SETUP": "持仓：需复核",
    "UNKNOWN_NO_FILING_INPUT": "无已提供的财报证据",
    "DECLARED_UNVERIFIED_REVIEW": "财报已录入，尚未核实",
    "STALE_FILING_REVIEW": "财报过期，需复核",
}


def _display_state(value: object) -> str:
    return safe(STATE_NAMES.get(value, value))


def _row(cells: list[object]) -> str:
    return "<tr>" + "".join("<td>" + safe(cell) + "</td>" for cell in cells) + "</tr>"


def _table(headers: list[str], rows: list[list[object]], empty: str) -> str:
    header = "".join("<th scope='col'>" + safe(h) + "</th>" for h in headers)
    if rows:
        body = "".join(_row(row) for row in rows)
    else:
        body = "<tr><td colspan='" + str(len(headers)) + "'>" + safe(empty) + "</td></tr>"
    return "<div class='table-wrap'><table><thead><tr>" + header + "</tr></thead><tbody>" + body + "</tbody></table></div>"


def render_html(report: dict) -> str:
    """Render only a canonical cockpit snapshot. Does not calculate investment signals."""
    if report.get("status") != "RESEARCH_COCKPIT":
        raise ValueError("INVALID_COCKPIT_FOR_HTML")
    s = report["summary"]
    holdings = [
        [p["symbol"], p["shares"], p["cost_basis_per_share"],
         p["reference_close"], p["market_value_excluding_fees"],
         p["unrealized_pnl_excluding_fees"], p["portfolio_weight_pct"],
         STATE_NAMES.get(p["research_action"], p["research_action"]),
         STATE_NAMES.get(p["financial_status"], p["financial_status"])]
        for p in report["holdings"]
    ]
    candidates = [
        [c["symbol"], c["first_seen_asof"],
         STATE_NAMES.get(c["research_state"], c["research_state"]),
         c["latest_reference_close"], STATE_NAMES.get(c["financial_status"], c["financial_status"]),
         c["evidence_source"], c["reason"]]
        for c in report["candidates"]
    ]
    summary = [
        ("持仓数", s["positions"]),
        ("长期候选", s["candidate_count"]),
        ("无法估值持仓", s["unvalued_positions"]),
        ("组合参考市值（元）", s["portfolio_marked_value_excluding_fees"]),
        ("浮动盈亏（元）", s["portfolio_unrealized_pnl_excluding_fees"]),
        ("财报证据覆盖", s["financial_evidence_count"]),
    ]
    cards = "".join(
        "<div class='metric'><span class='label'>" + safe(k)
        + "</span><strong>" + safe(v) + "</strong></div>" for k, v in summary
    )
    limitations = "".join("<li>" + safe(x) + "</li>" for x in report["limitations"])
    indices = (report.get("market_radar") or {}).get("indices", [])
    radar_table = _table(
        ["指数代码","趋势","数据日期","数据来源","判断依据"],
        [[x["symbol"], x["trend"], x["last_data_date"],
          x["source"], x["reason"]] for x in indices],
        "尚未提供指数行情；不推断市场周期。"
    )
    styles = """
    :root{color-scheme:light;font-family:system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif;
    background:#f5f7fb;color:#152137}*{box-sizing:border-box}body{margin:0}
    main{max-width:1220px;margin:auto;padding:28px 22px 75px}
    header{padding:28px 30px;border-radius:18px;background:#172849;color:white}
    h1{font-size:27px;margin:0 0 8px}h2{font-size:19px;margin:0 0 12px}
    p{line-height:1.65}.meta{opacity:.85;font-size:14px}
    .warning{border-left:4px solid #d69835;background:#fff7e8;padding:13px 18px;
    margin:20px 0;border-radius:6px;font-weight:600}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:20px 0}
    .metric{background:white;padding:17px;border-radius:12px;border:1px solid #e4e9f2}
    .label{font-size:12px;color:#5e7088;display:block;margin-bottom:8px}
    .metric strong{font-size:23px;font-variant-numeric:tabular-nums}
    section{background:white;border:1px solid #e4e9f2;border-radius:14px;padding:20px;
    margin-top:18px}.table-wrap{overflow:auto}table{width:100%;border-collapse:collapse;
    font-size:13px;text-align:left;white-space:nowrap}th{background:#eef2f8;
    color:#34445b}td,th{padding:12px 10px;border-bottom:1px solid #e9edf3}
    td{font-variant-numeric:tabular-nums}ul{padding-left:22px;line-height:1.9}
    .small{font-size:13px;color:#5e7088;overflow-wrap:anywhere}
    @media(max-width:640px){main{padding:12px}header{padding:19px}h1{font-size:22px}
    section{padding:13px}}
    """
    return (
        "<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>A股投资研究驾驶舱</title><style>" + styles + "</style></head><body><main>"
        "<header><h1>A股投资研究驾驶舱</h1><p class='meta'>数据截至 "
        + safe(report["asof"]) + " · 生成 UTC " + safe(report["generated_at_utc"])
        + "</p><p class='meta'>离线快照 · 非实时行情 · 研究辅助而非买卖指令</p></header>"
        "<div class='warning'>本页面不是投资建议。未认证的财报、未复权行情和缺失数据"
        "不能用于自动买入或卖出。</div>"
        "<div class='grid'>" + cards + "</div>"
        "<section><h2>我的持仓｜研究行动</h2>"
        + _table(["代码","股数","成本/股","参考价","参考市值","浮动盈亏",
                  "仓位%","研究状态","财报状态"], holdings, "尚无持仓记录")
        + "<p class='small'>参考价格与持仓成本由本地文件提供；市值未包含手续费、股息、税费和复权修正。</p></section>"
        "<section><h2>持续研究候选池</h2>"
        + _table(["代码","首次观察","当前研究状态","参考价","财报状态","行情来源","原因"],
                 candidates, "暂无合格候选记录")
        + "<p class='small'>长期候选不会仅因一天未触发技术条件就被删除。</p></section>"
        "<section><h2>风险与市场周期</h2><p>集中度："
        + safe(s["concentration_30pct_flag"]) + "</p><p>市场周期："
        + safe(s["market_cycle_radar"]) + "</p>" + radar_table + "</section>"
        "<section><h2>证据限制与待核实项</h2><ul>" + limitations + "</ul>"
        "<p class='small'>所有图表和表格均由同一份本地 JSON 快照生成。"
        "报告包含私人持仓信息，请勿上传到公开仓库。</p></section>"
        "</main></body></html>"
    )
