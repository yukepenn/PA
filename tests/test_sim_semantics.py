import unittest

import pandas as pd

from pa.sim.engine import SimEngine, activation_from_5m_bar_close
from pa.sim.models import BracketSpec, OrderSide, OrderStatus, OrderType, SimSessionMeta


def _bars(rows):
    df = pd.DataFrame(rows)
    df["ts_utc"] = pd.to_datetime(df["ts_utc"], utc=True, errors="raise")
    return df


class TestSimSemantics(unittest.TestCase):
    def test_market_activation_and_fill_at_open(self):
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
        df = _bars(
            [
                {"ts_utc": active_from, "open": 100.0, "high": 101.0, "low": 99.5, "close": 100.5},
            ]
        )
        fills = eng.process_bars(df)
        self.assertEqual(len(fills), 1)
        self.assertEqual(fills[0].price, 100.0)  # open
        self.assertEqual(eng.state.orders[o.order_id].status, OrderStatus.FILLED)
        self.assertEqual(eng.state.position.qty, 1)

    def test_stop_limit_triggered_then_fills_later(self):
        meta = SimSessionMeta.new("SPY", "2026-04-23")
        eng = SimEngine(meta)
        seen_5m = pd.Timestamp("2026-04-23 14:35:00", tz="UTC")
        active_from = activation_from_5m_bar_close(seen_5m)
        o = eng.place_order(
            side=OrderSide.BUY,
            type=OrderType.STOP_LIMIT,
            qty=1,
            stop_price=100.0,
            limit_price=100.5,
            placed_at_utc=seen_5m,
            active_from_utc=active_from,
        )

        # Bar 1: gaps above stop, but open > limit => trigger but no fill
        # Bar 2: trades down to <= limit => fill
        df = _bars(
            [
                {"ts_utc": active_from, "open": 101.0, "high": 101.2, "low": 100.8, "close": 101.0},
                {"ts_utc": active_from + pd.Timedelta(minutes=1), "open": 100.4, "high": 100.6, "low": 100.2, "close": 100.5},
            ]
        )
        fills = eng.process_bars(df)
        self.assertEqual(len(fills), 1)
        self.assertEqual(eng.state.orders[o.order_id].status, OrderStatus.FILLED)
        self.assertEqual(eng.state.position.qty, 1)

    def test_bracket_oco(self):
        meta = SimSessionMeta.new("SPY", "2026-04-23")
        eng = SimEngine(meta)
        seen_5m = pd.Timestamp("2026-04-23 14:35:00", tz="UTC")
        active_from = activation_from_5m_bar_close(seen_5m)
        legs = eng.place_bracket_order(
            entry_side=OrderSide.BUY,
            entry_type=OrderType.MARKET,
            qty=1,
            placed_at_utc=seen_5m,
            active_from_utc=active_from,
            bracket=BracketSpec(stop_loss=99.0, take_profit=101.0),
        )
        entry = legs["entry"]
        stop = legs["stop"]
        target = legs["target"]

        # Fill entry on first bar at open=100
        # Next bar triggers target (limit sell at 101) and should cancel stop via OCO.
        df = _bars(
            [
                {"ts_utc": active_from, "open": 100.0, "high": 100.2, "low": 99.9, "close": 100.1},
                {"ts_utc": active_from + pd.Timedelta(minutes=1), "open": 101.0, "high": 101.1, "low": 100.9, "close": 101.0},
            ]
        )
        eng.process_bars(df)
        self.assertEqual(eng.state.orders[entry.order_id].status, OrderStatus.FILLED)
        self.assertEqual(eng.state.orders[target.order_id].status, OrderStatus.FILLED)
        self.assertEqual(eng.state.orders[stop.order_id].status, OrderStatus.CANCELED)
        self.assertEqual(eng.state.position.qty, 0)

    def test_no_flip_rejection(self):
        meta = SimSessionMeta.new("SPY", "2026-04-23")
        eng = SimEngine(meta)
        seen_5m = pd.Timestamp("2026-04-23 14:35:00", tz="UTC")
        active_from = activation_from_5m_bar_close(seen_5m)

        # Open long 1
        eng.place_order(side=OrderSide.BUY, type=OrderType.MARKET, qty=1, placed_at_utc=seen_5m, active_from_utc=active_from)
        eng.process_bars(_bars([{"ts_utc": active_from, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}]))
        self.assertEqual(eng.state.position.qty, 1)

        # Now attempt to sell short 2 (would flip from +1 to -1) -> should REJECT when it would fill.
        o2 = eng.place_order(
            side=OrderSide.SELL_SHORT,
            type=OrderType.MARKET,
            qty=2,
            placed_at_utc=seen_5m,
            active_from_utc=active_from + pd.Timedelta(minutes=1),
        )
        eng.process_bars(_bars([{"ts_utc": active_from + pd.Timedelta(minutes=1), "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0}]))
        self.assertEqual(eng.state.orders[o2.order_id].status, OrderStatus.REJECTED)
        self.assertEqual(eng.state.position.qty, 1)


if __name__ == "__main__":
    unittest.main()

