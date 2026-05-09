#!/usr/bin/env python3
"""Regression tests for generate_declarative.py behavior."""

from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from generate_declarative import DeclarativePipelineGenerator, resolve_k8s_yaml  # noqa: E402
from syntax_helpers import ValidationHelpers  # noqa: E402


class ResolveK8sYamlRegressionTests(unittest.TestCase):
    """Cover path-vs-inline resolution behavior for --k8s-yaml."""

    def test_reads_existing_file_without_extension(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            yaml_path = Path(temp_dir) / "pod-template"
            yaml_content = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: demo\n"
            yaml_path.write_text(yaml_content, encoding="utf-8")

            self.assertEqual(resolve_k8s_yaml(str(yaml_path)), yaml_content)

    def test_missing_non_inline_value_raises_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "does-not-exist"
            with self.assertRaisesRegex(
                ValueError,
                "--k8s-yaml must be inline YAML content or an existing file path",
            ):
                resolve_k8s_yaml(str(missing_path))

    def test_missing_single_token_value_raises_error(self):
        with self.assertRaisesRegex(
            ValueError,
            "--k8s-yaml must be inline YAML content or an existing file path",
        ):
            resolve_k8s_yaml("definitely-missing-k8s-yaml-token")

    def test_inline_yaml_is_preserved(self):
        inline_yaml = "apiVersion: v1\nkind: Pod\nmetadata:\n  name: inline"
        self.assertEqual(resolve_k8s_yaml(inline_yaml), inline_yaml)


class StageListParsingRegressionTests(unittest.TestCase):
    """Lock stage key normalization and validation rules."""

    def test_parse_stage_list_normalizes_case_and_spacing(self):
        stages = ValidationHelpers.parse_stage_list(" Build,TEST,parallel-tests,custom_stage ")
        self.assertEqual(stages, ["build", "test", "parallel-tests", "custom_stage"])

    def test_parse_stage_list_rejects_invalid_keys(self):
        with self.assertRaisesRegex(ValueError, "Invalid stage key"):
            ValidationHelpers.parse_stage_list("build,Security Scan")

    def test_parse_stage_list_requires_at_least_one_stage(self):
        with self.assertRaisesRegex(ValueError, "At least one stage must be provided"):
            ValidationHelpers.parse_stage_list(" , , ")


class ParallelFailFastRegressionTests(unittest.TestCase):
    """Verify parallel fail-fast rendering combinations."""

    @staticmethod
    def _render_pipeline(options=None, parallel_fail_fast=True):
        config = {
            "name": "Parallel Fail Fast Regression",
            "stages": ["parallel-tests"],
            "parallel_fail_fast": parallel_fail_fast,
        }
        if options is not None:
            config["options"] = options
        return DeclarativePipelineGenerator(config).generate()

    def test_parallel_stage_includes_fail_fast_by_default(self):
        output = self._render_pipeline()
        self.assertIn("failFast true", output)

    def test_global_fail_fast_option_omits_redundant_stage_flag(self):
        output = self._render_pipeline(options={"parallelsAlwaysFailFast": True})
        self.assertIn("parallelsAlwaysFailFast()", output)
        self.assertNotIn("failFast true", output)

    def test_parallel_stage_can_disable_fail_fast(self):
        output = self._render_pipeline(parallel_fail_fast=False)
        self.assertNotIn("failFast true", output)
        self.assertNotIn("parallelsAlwaysFailFast()", output)


if __name__ == "__main__":
    unittest.main()
