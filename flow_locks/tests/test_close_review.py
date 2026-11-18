import sys
import unittest
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from flow_locks.close_review import three_complete, run, assess_close

def bars():
    return [
        {"date":f"2026-11-{day:02d}","close":4.5,"open":4.5,
         "high":4.6,"low":4.4,"turnover_yuan":1000}
        for day in (13,16,17,18)]

class CloseReviewTest(unittest.TestCase):
    def test_includes_today_not_future(self):
        f=[("2026-11-13",20),("2026-11-16",10),("2026-11-17",20),
           ("2026-11-18",80),("2026-11-19",99999)]
        res=three_complete(f,bars(),"2026-11-18")
        self.assertEqual(res["dates"],["2026-11-16","2026-11-17","2026-11-18"])
        self.assertAlmostEqual(res["pct"],110/3000*100,places=3)
        self.assertEqual(res["positive_days"],3)

    def test_missing_funds_closed(self):
        f=[("2026-11-16",10),("2026-11-17",20)]
        with self.assertRaises(ValueError):
            three_complete(f,bars(),"2026-11-18")

    def test_market_date_required(self):
        with self.assertRaises(ValueError):
            three_complete([],bars(),"2026-11-19")

    def test_before_close_rejected(self):
        result=run(["000100"],now=datetime(2026,11,18,5,0,tzinfo=timezone.utc))
        self.assertEqual(result["status"],"DATA_BLOCKED")

    @patch("flow_locks.close_review.daily_bars",side_effect=ValueError("bad quote"))
    def test_missing_daily_data_is_never_buy(self, unused):
        r=assess_close("000100",now=datetime(2026,11,18,8,0,tzinfo=timezone.utc),close_date="2026-11-18")
        self.assertFalse(r["buy_signal"])
        self.assertEqual(r["status"],"DATA_BLOCKED")

if __name__=="__main__": unittest.main()
