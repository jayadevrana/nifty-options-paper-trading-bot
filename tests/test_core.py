import unittest

from app.brokerage import calculate_option_roundtrip_charges
from app.config import settings


class BrokerageTests(unittest.TestCase):
    def test_option_roundtrip_charges_are_positive(self) -> None:
        result = calculate_option_roundtrip_charges(
            entry_credit_points=42.0,
            exit_debit_points=21.0,
            quantity=65,
        )
        self.assertGreater(result["total"], 0)
        self.assertGreater(result["stt"], 0)

    def test_start_date_is_tomorrow_from_build_context(self) -> None:
        self.assertEqual(settings.paper_start_date.isoformat(), "2026-03-26")


if __name__ == "__main__":
    unittest.main()
