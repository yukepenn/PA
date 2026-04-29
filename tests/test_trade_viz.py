import unittest

import pandas as pd

from pa.apps.replay_dash.trade_viz import derive_trade_episodes, planned_bracket_levels_at_entry


class TestTradeViz(unittest.TestCase):
    def test_open_episode_long_vwap(self):
        t0 = pd.Timestamp("2026-04-23 14:31:00", tz="UTC")
        ve = pd.Timestamp("2026-04-23 14:40:00", tz="UTC")
        sim_store = {
            "fills": [
                {"fill_id": "f1", "order_id": "o1", "side": "BUY", "qty": 1, "price": 100.0, "ts_utc": str(t0)},
            ]
        }
        open_ep, closed = derive_trade_episodes(sim_store, visible_end_utc=ve)
        self.assertIsNotNone(open_ep)
        self.assertEqual(open_ep.side, "LONG")
        self.assertEqual(open_ep.entry_ts_utc, t0)
        self.assertEqual(open_ep.exit_ts_utc, ve)
        self.assertAlmostEqual(open_ep.entry_px, 100.0)
        self.assertEqual(closed, [])

    def test_scale_in_then_flatten_close_cluster_vwap(self):
        t0 = pd.Timestamp("2026-04-23 14:31:00", tz="UTC")
        t1 = pd.Timestamp("2026-04-23 14:32:00", tz="UTC")
        t2 = pd.Timestamp("2026-04-23 14:33:00", tz="UTC")
        sim_store = {
            "fills": [
                {"fill_id": "f1", "order_id": "o1", "side": "BUY", "qty": 1, "price": 100.0, "ts_utc": str(t0)},
                {"fill_id": "f2", "order_id": "o2", "side": "BUY", "qty": 1, "price": 102.0, "ts_utc": str(t1)},
                {"fill_id": "f3", "order_id": "o3", "side": "SELL", "qty": 2, "price": 101.0, "ts_utc": str(t2)},
            ]
        }
        open_ep, closed = derive_trade_episodes(sim_store)
        self.assertIsNone(open_ep)
        self.assertEqual(len(closed), 1)
        ep = closed[0]
        self.assertEqual(ep.side, "LONG")
        self.assertAlmostEqual(ep.entry_px, 101.0)  # (100+102)/2
        self.assertAlmostEqual(ep.exit_px or 0.0, 101.0)

    def test_partial_exit_then_flatten_cluster_vwap(self):
        t0 = pd.Timestamp("2026-04-23 14:31:00", tz="UTC")
        t1 = pd.Timestamp("2026-04-23 14:32:00", tz="UTC")
        t2 = pd.Timestamp("2026-04-23 14:33:00", tz="UTC")
        sim_store = {
            "fills": [
                {"fill_id": "f1", "order_id": "o1", "side": "BUY", "qty": 3, "price": 100.0, "ts_utc": str(t0)},
                {"fill_id": "f2", "order_id": "o2", "side": "SELL", "qty": 1, "price": 101.0, "ts_utc": str(t1)},
                {"fill_id": "f3", "order_id": "o3", "side": "SELL", "qty": 2, "price": 99.0, "ts_utc": str(t2)},
            ]
        }
        open_ep, closed = derive_trade_episodes(sim_store)
        self.assertIsNone(open_ep)
        self.assertEqual(len(closed), 1)
        ep = closed[0]
        self.assertAlmostEqual(ep.exit_px or 0.0, (1 * 101.0 + 2 * 99.0) / 3.0)

    def test_planned_bracket_levels_at_entry(self):
        entry_id = "entry-123"
        sim_store = {
            "orders": [
                {"order_id": entry_id, "parent_order_id": None, "type": "MARKET"},
                {"order_id": "stop-1", "parent_order_id": entry_id, "type": "STOP", "stop_price": 99.0},
                {"order_id": "tgt-1", "parent_order_id": entry_id, "type": "LIMIT", "limit_price": 101.0},
                {"order_id": "noise", "parent_order_id": "other", "type": "STOP", "stop_price": 1.0},
            ]
        }
        sl, tp = planned_bracket_levels_at_entry(sim_store, entry_order_id=entry_id)
        self.assertEqual(sl, 99.0)
        self.assertEqual(tp, 101.0)


if __name__ == "__main__":
    unittest.main()

