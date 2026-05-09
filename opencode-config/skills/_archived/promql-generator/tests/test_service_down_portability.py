import unittest
from pathlib import Path


ALERTING_RULES = (
    Path(__file__).resolve().parents[1] / "examples" / "alerting_rules.yaml"
)


class ServiceDownPortabilityTests(unittest.TestCase):
    def _service_down_block(self) -> str:
        lines = ALERTING_RULES.read_text(encoding="utf-8").splitlines()
        start = None
        for idx, line in enumerate(lines):
            if line.strip() == "- alert: ServiceDown":
                start = idx
                break

        self.assertIsNotNone(start, "ServiceDown alert block not found")

        block_lines = []
        for idx in range(start, len(lines)):
            if idx > start and lines[idx].startswith("      - alert:"):
                break
            block_lines.append(lines[idx])

        return "\n".join(block_lines)

    def test_service_down_expr_is_portable(self) -> None:
        block = self._service_down_block()
        expr_lines = [line.strip() for line in block.splitlines() if "expr:" in line]
        self.assertEqual(expr_lines, ["expr: up == 0"])

    def test_optional_scoped_variant_is_documented(self) -> None:
        block = self._service_down_block()
        self.assertIn(
            '# Optional scoped variant: up{job="api-server"} == 0',
            block,
        )


if __name__ == "__main__":
    unittest.main()
