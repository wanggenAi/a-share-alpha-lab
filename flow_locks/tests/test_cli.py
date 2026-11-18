import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from flow_locks.cli import market_id,three_day_strength,inspect,is_trading

class TestFlowLocks(unittest.TestCase):
    def test_codes(self):
        self.assertEqual(market_id("000100"),"0.000100")
        self.assertEqual(market_id("600206"),"1.600206")
        with self.assertRaises(ValueError): market_id("100")

    def test_only_complete_days_and_weighted_ratio(self):
        dates=["2026-11-13","2026-11-16","2026-11-17","2026-11-18"]
        flows=list(zip(dates,[20,40,30,999999]))
        quotes=[(d,5.0,100,1000) for d in dates]
        r=three_day_strength(flows,quotes,"2026-11-18")
        self.assertEqual(r["main_strength_pct"],3.0)
        self.assertEqual(r["main_net_yuan"],90)
        self.assertEqual(r["positive_days"],3)

    def test_missing_day_blocks(self):
        flow=[("2026-11-13",20),("2026-11-17",30)]
        quotes=[(d,5.0,100,1000) for d in
                ["2026-11-13","2026-11-16","2026-11-17"]]
        with self.assertRaises(ValueError):
            three_day_strength(flow,quotes,"2026-11-18")

    def test_session(self):
        self.assertTrue(is_trading(datetime(2026,11,18,2,0,tzinfo=timezone.utc)))
        self.assertFalse(is_trading(datetime(2026,11,18,4,0,tzinfo=timezone.utc)))

    @patch("flow_locks.cli.funds",side_effect=ValueError("rate limited"))
    def test_network_failure_never_buy(self, mock_funds):
        r=inspect("000100",datetime(2026,11,18,2,0,tzinfo=timezone.utc))
        self.assertEqual(r["status"],"DATA_BLOCKED")
        self.assertFalse(r["buy_signal"])

if __name__=="__main__": unittest.main()
