import unittest

import pandas as pd

from pa.apps.replay_dash.marker_keys import decode_marker_key, encode_marker_key
from pa.sim.engine import SimEngine, activation_from_5m_bar_close
from pa.sim.models import OrderSide, OrderType, SimSessionMeta


class TestWorkingOrderDragV1(unittest.TestCase):
    def test_marker_key_roundtrip(self):
        k = encode_marker_key(scope="sim", field="entry_limit", entity_id="order-123")
        mk = decode_marker_key(k)
        self.assertIsNotNone(mk)
        assert mk is not None
        self.assertEqual(mk.scope, "sim")
        self.assertEqual(mk.field, "entry_limit")
        self.assertEqual(mk.entity_id, "order-123")

    def test_modify_order_price_limit(self):
        meta = SimSessionMeta.new("SPY", "2026-04-23")
        eng = SimEngine(meta)
        seen_5m = pd.Timestamp("2026-04-23 14:35:00", tz="UTC")
        active_from = activation_from_5m_bar_close(seen_5m)
        o = eng.place_order(
            side=OrderSide.BUY,
            type=OrderType.LIMIT,
            qty=1,
            limit_price=100.0,
            placed_at_utc=seen_5m,
            active_from_utc=active_from,
        )
        o2 = eng.modify_order_price(o.order_id, limit_price=101.0)
        self.assertEqual(o2.order_id, o.order_id)
        self.assertEqual(float(eng.state.orders[o.order_id].limit_price or 0.0), 101.0)

    def test_modify_order_price_rejects_market(self):
        meta = SimSessionMeta.new("SPY", "2026-04-23")
        eng = SimEngine(meta)
        seen_5m = pd.Timestamp("2026-04-23 14:35:00", tz="UTC")
        active_from = activation_from_5m_bar_close(seen_5m)
        o = eng.place_order(
            side=OrderSide.BUY,
            type=OrderType.MARKET,
            qty=1,
            placed_at_utc=seen_5m,
            active_from_utc=active_from,
        )
        with self.assertRaises(ValueError):
            eng.modify_order_price(o.order_id, limit_price=101.0)

    def test_modify_order_price_requires_correct_field(self):
        meta = SimSessionMeta.new("SPY", "2026-04-23")
        eng = SimEngine(meta)
        seen_5m = pd.Timestamp("2026-04-23 14:35:00", tz="UTC")
        active_from = activation_from_5m_bar_close(seen_5m)
        o = eng.place_order(
            side=OrderSide.BUY,
            type=OrderType.STOP,
            qty=1,
            stop_price=100.0,
            placed_at_utc=seen_5m,
            active_from_utc=active_from,
        )
        with self.assertRaises(ValueError):
            eng.modify_order_price(o.order_id, limit_price=101.0)


if __name__ == "__main__":
    unittest.main()

