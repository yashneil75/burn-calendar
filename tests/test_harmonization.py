import sys
import unittest
from datetime import datetime
from unittest.mock import patch
from urllib.error import URLError
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
import build_calendar
import fit_model
import firms_api
import numpy as np
from boundary import within_california, california
from aggregate import aggregate_observations


class HarmonizationTests(unittest.TestCase):
    def test_firms_retries_transient_network_failures(self):
        from datetime import date
        class Headers:
            def get_content_charset(self): return "utf-8"
        class Response:
            headers = Headers()
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return b"latitude,longitude\n38,-121\n"
        with patch.dict('os.environ', {'FIRMS_MAP_KEY': 'test'}), \
             patch.object(firms_api, 'urlopen', side_effect=[URLError('offline'), URLError('offline'), Response()]) as request, \
             patch.object(firms_api.time, 'sleep'):
            rows = firms_api.fetch_rows('VIIRS_NOAA20_NRT', [-124.5,32.5,-114.1,42], 1, date(2026,11,15))
        self.assertEqual(request.call_count, 3)
        self.assertEqual(rows[0]['latitude'], '38')
    def test_model_validation_uses_production_cap(self):
        prediction = fit_model.predict(np.array([[100.0]]), np.array([1.0]), 0.0,
                                       np.array([0.0]), np.array([1.0]))
        self.assertEqual(float(prediction[0]), 500.0)
    def test_california_filter_excludes_nevada_but_includes_boundary(self):
        from shapely.geometry import mapping
        geometry = mapping(california())
        ring = geometry["coordinates"][0][0] if geometry["type"] == "MultiPolygon" else geometry["coordinates"][0]
        lon, lat = ring[0]
        self.assertEqual(within_california([-122.4194, -119.8138, lon], [37.7749, 39.5296, lat]).tolist(), [True, False, True])

    def test_aggregation_filters_outside_state(self):
        base = {"satellite": "N20", "acq_date": "2026-11-05", "acq_time": "2000",
                "confidence": "n", "daynight": "D", "frp": "10"}
        rows = [{**base, "latitude": 37.7749, "longitude": -122.4194},
                {**base, "latitude": 39.5296, "longitude": -119.8138}]
        passes = aggregate_observations(rows, "california-state")
        self.assertEqual(sum(p["detections"] for p in passes), 1)
    def test_noaa20_refresh_and_standard_quality_precedence(self):
        row = {"satellite": "N20", "latitude": "38", "longitude": "-121",
               "acq_date": "2026-11-05", "acq_time": "1200", "confidence": "n",
               "daynight": "D", "frp": "10", "scan": "0.4", "track": "0.4"}
        nrt = build_calendar.entries_from_rows([row], "VIIRS_NOAA20_NRT", "california-state")
        self.assertEqual(nrt["2026-11-05"]["sensor"], "NOAA20")
        self.assertEqual(nrt["2026-11-05"]["viirs_cells"], 1)
        sp = build_calendar.entries_from_rows([{**row, "type": "0"}], "VIIRS_NOAA20_SP", "california-state")
        merged = build_calendar.merge_days(sp, nrt)
        self.assertEqual(merged["2026-11-05"]["status"], "sp")

    def test_refresh_routes_noaa_data_and_writes_sensor_label(self):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2026, 11, 15, tzinfo=tz)
        row = {"satellite": "N20", "latitude": "38", "longitude": "-121",
               "acq_date": "2026-11-05", "acq_time": "2000", "confidence": "n",
               "daynight": "D", "frp": "10"}
        def fake_fetch(source, bbox, n, start):
            if source == "VIIRS_NOAA20_NRT" and start.isoformat() <= row["acq_date"] <= (start + build_calendar.timedelta(days=n-1)).isoformat():
                return [row]
            return []
        with patch.object(build_calendar, "fetch_rows", side_effect=fake_fetch) as fetch, \
             patch.object(build_calendar, "load_state", return_value={}), \
             patch.object(build_calendar, "load_map_state", return_value={}), \
             patch.object(build_calendar, "atomic_write_json") as write, \
             patch.object(build_calendar, "datetime", FixedDatetime), \
             patch.object(sys, "argv", ["build_calendar.py"]):
            build_calendar.main()
        sources = {call.args[0] for call in fetch.call_args_list}
        self.assertIn("VIIRS_NOAA20_NRT", sources)
        payload = next(c.args[1] for c in write.call_args_list if c.args[0] == build_calendar.CALENDAR_PATH)
        self.assertEqual(payload["daily"][0]["sensor"], "NOAA20")
        map_data = next(c.args[1] for c in write.call_args_list if c.args[0] == build_calendar.MAP_PATH)
        self.assertGreater(len(map_data["cells"]), 0)

    def test_refresh_checks_prior_year_for_standard_processing_upgrade(self):
        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return cls(2027, 1, 15, tzinfo=tz)
        with patch.object(build_calendar, "fetch_rows", return_value=[]) as fetch, \
             patch.object(build_calendar, "load_state", return_value={}), \
             patch.object(build_calendar, "load_map_state", return_value={}), \
             patch.object(build_calendar, "atomic_write_json"), \
             patch.object(build_calendar, "datetime", FixedDatetime), \
             patch.object(sys, "argv", ["build_calendar.py"]):
            build_calendar.main()
        starts = [call.args[3] for call in fetch.call_args_list if call.args[0] == "VIIRS_NOAA20_SP"]
        self.assertLess(min(starts).year, 2027)

    def test_map_and_calendar_upgrade_together(self):
        days = {"2026-11-05": {"status": "sp", "activity": 5}}
        grids = {"2026-11-05": [[1, 2, -121, 38, 5]]}
        build_calendar.merge_days_and_map(days, grids,
            {"2026-11-05": {"status": "nrt", "activity": 9}},
            {"2026-11-05": [[1, 2, -121, 38, 9]]})
        self.assertEqual((days["2026-11-05"]["activity"], grids["2026-11-05"][0][4]), (5, 5))
        build_calendar.merge_days_and_map(days, grids,
            {"2026-11-05": {"status": "sp", "activity": 7}},
            {"2026-11-05": [[1, 2, -121, 38, 7]]})
        self.assertEqual((days["2026-11-05"]["activity"], grids["2026-11-05"][0][4]), (7, 7))


if __name__ == "__main__":
    unittest.main()
