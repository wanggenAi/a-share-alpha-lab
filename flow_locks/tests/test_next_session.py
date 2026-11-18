import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from flow_locks.next_session import gate,compile_report,display

DATE="2026-11-18"
def valid():
    return dict(symbol="000100",market_date=DATE,status="RESEARCH_TRIPLE_PASS",
        close=4.77,high=4.82,low=4.65,chase_risk_flag=False,
        trend_lock={"pass":True},main_funds_lock={"pass":True},
        activity_lock={"pass":True})

class TestNextSession(unittest.TestCase):
    def test_eligible_is_watch_not_buy(self):
        r=gate(valid(),DATE)
        self.assertEqual(r["decision"],"WATCH_PENDING_VALUE_AND_TOMORROW")
        self.assertFalse(r["buy_signal"])
        self.assertFalse(r["order_permitted"])
        self.assertEqual(r["hypothetical_entry_yuan"],4.83)
        self.assertEqual(r["hypothetical_stop_yuan"],4.64)
        self.assertLessEqual(r["planned_risk_yuan"],100)
        self.assertEqual(r["paper_shares"]%100,0)
    def test_mismatched_date_blocks(self):
        self.assertEqual(gate(valid(),"2026-11-19")["reason"],"DATA_DATE_MISMATCH")
    def test_missing_provider_blocks(self):
        x=valid();x["status"]="DATA_BLOCKED"
        self.assertEqual(gate(x,DATE)["reason"],"PROVIDER_DATA_MISSING")
    def test_missing_lock_blocks(self):
        x=valid();x["activity_lock"]={"pass":None}
        self.assertEqual(gate(x,DATE)["reason"],"TRIPLE_LOCK_NOT_MET" if x["status"]!="RESEARCH_TRIPLE_PASS" else "LOCK_EVIDENCE_MISSING")
    def test_chase_risk_blocks(self):
        x=valid();x["chase_risk_flag"]=True
        self.assertEqual(gate(x,DATE)["reason"],"CHASE_RISK")
    def test_risk_budget_blocks(self):
        self.assertEqual(gate(valid(),DATE,max_risk=10)["reason"],"RISK_BUDGET_BELOW_ONE_LOT")
    def test_bad_prices_block(self):
        x=valid();x["low"]=None
        self.assertEqual(gate(x,DATE)["reason"],"INVALID_PRICE_OR_BUDGET")
    def test_absent_report_is_no_trade(self):
        out=compile_report({})
        self.assertFalse(out["buy_signal"])
        self.assertEqual(out["status"],"DATA_BLOCKED")
    def test_partial_report_does_not_conflate_missing_with_no_candidate(self):
        data={"market_date_cn":DATE,"status":"PARTIAL_OR_BLOCKED",
              "stocks":[valid(),{"symbol":"002222","market_date":DATE,"status":"DATA_BLOCKED"}]}
        out=compile_report(data)
        self.assertEqual(out["data_missing"],1)
        self.assertEqual(len(out["watch"]),1)
        self.assertIn("002222",display(out))
    def test_overwide_stop_blocks(self):
        x=valid();x["high"]=6.20
        self.assertEqual(gate(x,DATE)["reason"],"STOP_DISTANCE_TOO_WIDE")
if __name__=="__main__":unittest.main()
