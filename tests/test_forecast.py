import sys
import unittest
from datetime import date, timedelta
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from forecast_experimental import make_forecast


class FakeResult:
    def quantile(self, q):
        return np.full(8, np.log1p({0.1: 1.0, 0.5: 2.0, 0.9: 3.0}[q]))


class FakeModel:
    def forecast(self, context, prediction_length):
        self.context = context
        self.horizon = prediction_length
        return FakeResult()


class ForecastTests(unittest.TestCase):
    def test_future_predictions_never_replace_or_consume_today(self):
        today = date(2026, 11, 15)
        rows = [{'date': (today-timedelta(days=i)).isoformat(), 'activity': 10.0} for i in range(1, 40) if i != 3]
        rows.append({'date': today.isoformat(), 'activity': 99999.0})
        model = FakeModel()
        output = make_forecast({'daily': rows, 'unit': 'cells'}, model, today)
        self.assertEqual(output['origin_utc_date'], '2026-11-14')
        self.assertEqual(output['predictions'][0]['date'], '2026-11-16')
        self.assertEqual(output['predictions'][-1]['date'], '2026-11-22')
        self.assertTrue(np.isnan(model.context[-3]))
        self.assertAlmostEqual(float(np.nanmax(model.context)), np.log1p(10.0), places=6)
        self.assertEqual(model.horizon, 8)

    def test_stale_data_withholds_forecast(self):
        rows = [{'date': f'2026-10-{i:02d}', 'activity': 10.0} for i in range(1, 30)]
        with self.assertRaisesRegex(ValueError, 'more than three days old'):
            make_forecast({'daily': rows}, FakeModel(), date(2026, 11, 15))


if __name__ == '__main__':
    unittest.main()
