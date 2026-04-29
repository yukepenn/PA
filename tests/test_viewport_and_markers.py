import unittest

import pandas as pd
import plotly.graph_objects as go

from pa.apps.replay_dash.price_labels import PriceMarkerStyle, add_price_marker
from pa.apps.replay_dash.viewport import rth_session_x_range_utc


class TestViewportAndMarkers(unittest.TestCase):
    def test_rth_session_range_is_utc_and_duration(self):
        xr = rth_session_x_range_utc("2026-04-23")
        self.assertIsNotNone(xr)
        x0, x1 = xr
        self.assertEqual(str(x0.tzinfo), "UTC")
        self.assertEqual(str(x1.tzinfo), "UTC")
        self.assertEqual(x1 - x0, pd.Timedelta(hours=6, minutes=30))

    def test_price_marker_name_contract(self):
        fig = go.Figure()
        add_price_marker(
            fig,
            y=100.0,
            text="Draft SL 100.00",
            name="draft:stop_loss",
            style=PriceMarkerStyle(color="rgba(0,0,0,1)"),
            active=False,
            yshift_px=0,
        )
        self.assertTrue(len(fig.layout.shapes) >= 1)
        self.assertTrue(len(fig.layout.annotations) >= 1)
        self.assertEqual(fig.layout.shapes[-1].name, "draft:stop_loss")
        self.assertEqual(fig.layout.annotations[-1].name, "draft:stop_loss")


if __name__ == "__main__":
    unittest.main()

