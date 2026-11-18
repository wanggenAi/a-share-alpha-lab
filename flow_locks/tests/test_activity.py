import sys
import unittest
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from flow_locks.activity import relative_volume, LABELS

CN=ZoneInfo("Asia/Shanghai")
def sample(days=21):
    base=date(2026,10,1)
    sessions=[base+timedelta(days=i) for i in range(65) if (base+timedelta(days=i)).weekday()<5][-days:]
    bars=[]
    for d in sessions:
        for label in ["09:35","09:40"]:
            h,m=map(int,label.split(":"))
            stamp=datetime(d.year,d.month,d.day,h,m,tzinfo=CN)
            bars.append((stamp,200 if d==sessions[-1] else 100))
    now=datetime(sessions[-1].year,sessions[-1].month,sessions[-1].day,9,42,tzinfo=CN)
    return bars,now

class ActivityTest(unittest.TestCase):
    def test_standard_labels(self):
        self.assertEqual(len(LABELS),48)
        self.assertEqual(LABELS[0],"09:35")
        self.assertEqual(LABELS[-1],"15:00")

    def test_same_clock_ratio(self):
        bars,now=sample()
        r=relative_volume(bars,now)
        self.assertEqual(r["same_time_volume_ratio"],2.0)
        self.assertTrue(r["pass"])
        self.assertEqual(r["comparison_days"],20)

    def test_future_incomplete_ignored(self):
        bars,now=sample()
        bars.append((now+timedelta(minutes=3),9_000_000))
        self.assertEqual(relative_volume(bars,now)["same_time_volume_ratio"],2)

    def test_missing_session_slot_rejected(self):
        bars,now=sample()
        del bars[0]
        with self.assertRaises(ValueError):
            relative_volume(bars,now)

    def test_no_same_time_due_to_stale(self):
        bars,now=sample()
        with self.assertRaises(ValueError):
            relative_volume(bars,now.replace(hour=10,minute=20))

    def test_insufficient_history_rejected(self):
        bars,now=sample(5)
        with self.assertRaises(ValueError):
            relative_volume(bars,now)

if __name__=="__main__":unittest.main()
