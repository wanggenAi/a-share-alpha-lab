"""Honest intraday relative-volume gate using completed 5-minute candles only."""
from __future__ import annotations
from datetime import datetime, time, timedelta
import math
from .cli import CN, market_id, query

def time_labels():
    morning = [(datetime(2000,1,1,9,35)+timedelta(minutes=5*i)).strftime("%H:%M") for i in range(24)]
    afternoon = [(datetime(2000,1,1,13,5)+timedelta(minutes=5*i)).strftime("%H:%M") for i in range(24)]
    return morning + afternoon

LABELS = time_labels()

def five_minute_volume(symbol, limit=1600):
    """Provider returns 5m OHLCV; volume is in lots, uniformly comparable per ticker."""
    obj = query("kline/get",{
        "secid":market_id(symbol),"klt":5,"fqt":0,"end":"20500101","lmt":limit,
        "fields1":"f1,f2,f3,f4,f5,f6",
        "fields2":"f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
    })
    lines=obj.get("klines")
    if not isinstance(lines,list) or not lines:
        raise ValueError("5m bars unavailable")
    out=[]
    for raw in lines:
        c=str(raw).split(",")
        if len(c)<7: raise ValueError("malformed 5m row")
        stamp=datetime.strptime(c[0],"%Y-%m-%d %H:%M").replace(tzinfo=CN)
        vol=float(c[5])
        if not math.isfinite(vol) or vol<0: raise ValueError("invalid 5m volume")
        out.append((stamp,vol))
    if [x[0] for x in out]!=sorted(x[0] for x in out):
        raise ValueError("out of order 5m bars")
    return out

def relative_volume(bars, now, *, previous_sessions=20, threshold=1.5, stale_after=12):
    """Time-matched whole-day cumulative volume to the last definitely complete 5m bar.

    A vendor's newest partially formed bar is ignored. Past 20 sessions must have
    every slot up to the comparison time, otherwise fail closed.
    """
    current=now.astimezone(CN)
    today=current.date().isoformat()
    # Require the bar to have finished at least 30 seconds ago.
    eligible=[(stamp,vol) for stamp,vol in bars
              if stamp.astimezone(CN).date().isoformat()==today
              and stamp.astimezone(CN)+timedelta(seconds=30)<=current
              and stamp.astimezone(CN).strftime("%H:%M") in LABELS]
    if not eligible: raise ValueError("no completed current-day 5m candles")
    newest=max(stamp for stamp,_ in eligible)
    age=(current-newest).total_seconds()/60
    if age<0 or age>stale_after: raise ValueError("completed 5m bar stale")
    slot=newest.strftime("%H:%M")
    selected_slots=LABELS[:LABELS.index(slot)+1]
    all_sessions={}
    for stamp,vol in bars:
        local=stamp.astimezone(CN)
        day=local.date().isoformat()
        label=local.strftime("%H:%M")
        if day>today or label not in LABELS:
            continue
        session=all_sessions.setdefault(day,{})
        if label in session:
            raise ValueError("duplicate 5m candle")
        if day==today and stamp+timedelta(seconds=30)>current:
            continue
        session[label]=vol
    past_dates=sorted(d for d in all_sessions if d<today)
    if len(past_dates)<previous_sessions:
        raise ValueError("insufficient historical 5m sessions")
    past_dates=past_dates[-previous_sessions:]
    chosen=[today]+past_dates
    if any(any(s not in all_sessions.get(d,{}) for s in selected_slots) for d in chosen):
        raise ValueError("incomplete same-minute 5m volumes")
    today_volume=sum(all_sessions[today][s] for s in selected_slots)
    baseline=sum(sum(all_sessions[d][s] for s in selected_slots) for d in past_dates)/previous_sessions
    if baseline<=0: raise ValueError("zero volume baseline")
    ratio=today_volume/baseline
    return {
        "pass": ratio>=threshold,
        "threshold":threshold, "comparison_end_cn":newest.isoformat(timespec="minutes"),
        "data_age_minutes":round(age,2),
        "today_cumulative_lots":round(today_volume,2),
        "historical_mean_lots":round(baseline,2),
        "same_time_volume_ratio":round(ratio,4),
        "comparison_days":previous_sessions,
        "source":"unadjusted 5m market candles; 20 complete prior sessions"
    }
