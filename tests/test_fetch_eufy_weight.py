import unittest

from scripts import fetch_eufy_weight


class FetchEufyWeightTest(unittest.TestCase):
    def test_extracts_scale_data_weight_with_parent_update_time(self):
        reading = fetch_eufy_weight._extract_latest_weight({
            "res_code": 1,
            "data": [
                {
                    "device_id": "scale-1",
                    "customer_id": "user-1",
                    "update_time": 1_700_000_000,
                    "create_time": 1_699_999_900,
                    "scale_data": {
                        "weight": 717,
                    },
                },
                {
                    "device_id": "scale-1",
                    "customer_id": "user-1",
                    "update_time": 1_700_003_600,
                    "create_time": 1_700_003_500,
                    "scale_data": {
                        "weight": 720,
                    },
                },
            ],
        })

        self.assertEqual(reading.weight_kg, 72.0)
        self.assertEqual(reading.measured_at, "2023-11-14T23:13:20Z")
        self.assertEqual(reading.measured_at_source, "update_time")

    def test_falls_back_to_generic_weight_records(self):
        reading = fetch_eufy_weight._extract_latest_weight({
            "records": [
                {
                    "weight": 717,
                    "timestamp": 1_700_000_000,
                },
            ],
        })

        self.assertEqual(reading.weight_kg, 71.7)
        self.assertEqual(reading.measured_at, "2023-11-14T22:13:20Z")
        self.assertEqual(reading.measured_at_source, "timestamp")

    def test_ignores_zero_time_values(self):
        reading = fetch_eufy_weight._extract_latest_weight({
            "data": [
                {
                    "update_time": 0,
                    "create_time": 0,
                    "scale_data": {
                        "weight": 717,
                    },
                },
            ],
        })

        self.assertEqual(reading.weight_kg, 71.7)
        self.assertIsNone(reading.measured_at)
        self.assertIsNone(reading.measured_at_source)


if __name__ == "__main__":
    unittest.main()
