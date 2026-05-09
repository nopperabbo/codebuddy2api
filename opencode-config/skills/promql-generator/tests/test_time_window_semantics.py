import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
COMMON_QUERIES = SKILL_DIR / "examples" / "common_queries.promql"
PROMQL_PATTERNS = SKILL_DIR / "references" / "promql_patterns.md"


class TimeWindowSemanticsTests(unittest.TestCase):
    def test_common_queries_use_filtering_not_zero_masking(self) -> None:
        text = COMMON_QUERIES.read_text(encoding="utf-8")

        expected_queries = [
            "http_requests_total and on() (hour() >= 9 and hour() < 17)",
            "http_requests_total and on() (day_of_week() >= 1 and day_of_week() <= 5)",
            "http_requests_total and on() (day_of_week() == 0 or day_of_week() == 6)",
        ]
        for query in expected_queries:
            self.assertIn(query, text)

        legacy_queries = [
            "http_requests_total * scalar((hour() >= bool 9) * (hour() < bool 17))",
            "http_requests_total * scalar((day_of_week() >= bool 1) * (day_of_week() <= bool 5))",
            "http_requests_total * scalar((day_of_week() == bool 0) + (day_of_week() == bool 6))",
        ]
        for query in legacy_queries:
            self.assertNotIn(query, text)

    def test_common_queries_include_utc_note(self) -> None:
        text = COMMON_QUERIES.read_text(encoding="utf-8")
        self.assertIn("hour() and day_of_week() evaluate in UTC", text)

    def test_reference_patterns_use_filtering_not_zero_masking(self) -> None:
        text = PROMQL_PATTERNS.read_text(encoding="utf-8")

        expected_queries = [
            "metric and on() (hour() >= 9 and hour() < 17)",
            "metric and on() (day_of_week() >= 1 and day_of_week() <= 5)",
            "metric and on() (day_of_week() == 0 or day_of_week() == 6)",
        ]
        for query in expected_queries:
            self.assertIn(query, text)

        legacy_queries = [
            "metric * scalar((hour() >= bool 9) * (hour() < bool 17))",
            "metric * scalar((day_of_week() >= bool 1) * (day_of_week() <= bool 5))",
            "metric * scalar((day_of_week() == bool 0) + (day_of_week() == bool 6))",
        ]
        for query in legacy_queries:
            self.assertNotIn(query, text)

    def test_reference_patterns_include_utc_note(self) -> None:
        text = PROMQL_PATTERNS.read_text(encoding="utf-8")
        self.assertIn("hour() and day_of_week() evaluate in UTC", text)


if __name__ == "__main__":
    unittest.main()
