import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from flow_locks.market_scan import (
    parse_market_record, is_main_board, rank_candidates,
    assemble_pages, collect, run_market_scan
)

def stock(code, mk, ratio=5.0, name="测试股份", turnover=100_000_000, stamp=1794970800):
    net=round(turnover*ratio/100,2)
    return {"f12":code,"f13":mk,"f14":name,"f2":5.0,"f3":1.0,
            "f6":turnover,"f8":3.2,"f62":net,"f184":ratio,"f124":stamp}

class MarketScanTest(unittest.TestCase):
    def test_validates_main_board_and_excludes_special_baskets(self):
        self.assertTrue(is_main_board("000100",0))
        self.assertTrue(is_main_board("600206",1))
        self.assertFalse(is_main_board("300750",0))
        self.assertFalse(is_main_board("688256",1))
        self.assertFalse(is_main_board("832111",0))

    def test_detects_wrong_units(self):
        x=stock("000100",0,5)
        self.assertTrue(parse_market_record(x)["flow_ratio_verified"])
        x["f62"]=1
        self.assertFalse(parse_market_record(x)["flow_ratio_verified"])

    def test_missing_and_sentinel(self):
        self.assertIsNone(parse_market_record({"f12":"600206","f13":1,"f14":"test","f2":"-","f6":2}))
        self.assertIsNone(parse_market_record(None))

    def test_excludes_st_and_high_risk_and_other_boards(self):
        a=stock("600206",1,6)
        b=stock("000100",0,5,name="ST测试")
        c=stock("300750",0,9)
        d=stock("600584",1,5.5,turnover=5_000_000)
        result=rank_candidates([a,b,c,d])
        self.assertEqual([r["symbol"] for r in result],["600206"])

    def test_page_integrity(self):
        a=stock("000100",0);b=stock("600206",1);c=stock("603993",1)
        rows=assemble_pages({1:[a,b],2:[c]},3,page_size=2)
        self.assertEqual(len(rows),3)
        with self.assertRaises(ValueError):
            assemble_pages({1:[a,b]},3,page_size=2)
        with self.assertRaises(ValueError):
            assemble_pages({1:[a,b],2:[b]},3,page_size=2)
        with self.assertRaises(ValueError):
            assemble_pages({1:[a],2:[c]},3,page_size=2)

    @patch("flow_locks.market_scan.fetch_page")
    def test_partial_market_never_ranked(self, mock):
        mock.return_value=(250,[stock("000100",0)]*100)
        r=collect(max_pages=1,pause=0)
        self.assertEqual(r["status"],"PARTIAL_DO_NOT_RANK")
        self.assertEqual(r["candidates"],[])
        self.assertFalse(r["all_pages_complete"])

    @patch("flow_locks.market_scan.fetch_page")
    def test_universe_changed_fails_closed(self, mock):
        a=[stock(f"000{i:03d}",0) for i in range(100)]
        mock.side_effect=[(150,a),(151,[stock("600206",1)]*50)]
        r=collect(pause=0)
        self.assertEqual(r["status"],"PARTIAL_DO_NOT_RANK")
        self.assertTrue(r["errors"])

    @patch("flow_locks.market_scan.collect",side_effect=RuntimeError("timeout"))
    def test_error_never_buy(self,mock):
        r=run_market_scan(deep=1,pause=0)
        self.assertEqual(r["status"],"DATA_BLOCKED")
        self.assertFalse(r["buy_signal"])

if __name__=="__main__": unittest.main()
