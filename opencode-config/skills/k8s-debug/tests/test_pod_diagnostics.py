#!/usr/bin/env python3
"""Regression tests for pod_diagnostics.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import pathlib
import sys
import unittest
from typing import List, Sequence, Tuple
from unittest.mock import patch


sys.dont_write_bytecode = True

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "pod_diagnostics.py"
SPEC = importlib.util.spec_from_file_location("pod_diagnostics", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load pod_diagnostics module from {SCRIPT_PATH}")
pod_diagnostics = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pod_diagnostics)

KubectlResponse = Tuple[str, str, int]
ExpectedCall = Tuple[Sequence[str], KubectlResponse]


class PodDiagnosticsInitContainerTests(unittest.TestCase):
    def _run_with_expected_calls(self, expected_calls: List[ExpectedCall]) -> str:
        pending = list(expected_calls)

        def fake_run(args: Sequence[str], timeout: int = 30) -> KubectlResponse:
            del timeout  # Assert command sequence/args; timeout variations are not relevant here.
            self.assertTrue(pending, f"Unexpected kubectl call: {list(args)}")
            expected_args, response = pending.pop(0)
            self.assertEqual(list(args), list(expected_args))
            return response

        stdout_buffer = io.StringIO()
        with patch.object(pod_diagnostics, "run_kubectl", side_effect=fake_run):
            with contextlib.redirect_stdout(stdout_buffer):
                pod_diagnostics.get_pod_info("demo-pod", "demo-ns")

        self.assertFalse(pending, f"Expected kubectl calls were not consumed: {pending}")
        return stdout_buffer.getvalue()

    def test_init_container_previous_logs_message_when_not_terminated(self) -> None:
        output = self._run_with_expected_calls(
            [
                (["get", "pod", "demo-pod", "-n", "demo-ns", "-o", "wide"], ("pod wide", "", 0)),
                (["describe", "pod", "demo-pod", "-n", "demo-ns"], ("pod describe", "", 0)),
                (["get", "pod", "demo-pod", "-n", "demo-ns", "-o", "yaml"], ("pod yaml", "", 0)),
                (
                    [
                        "get",
                        "events",
                        "-n",
                        "demo-ns",
                        "--field-selector",
                        "involvedObject.name=demo-pod",
                        "--sort-by=.lastTimestamp",
                    ],
                    ("event list", "", 0),
                ),
                (
                    ["get", "pod", "demo-pod", "-n", "demo-ns", "-o", "jsonpath={.spec.containers[*].name}"],
                    ("app", "", 0),
                ),
                (
                    ["logs", "demo-pod", "-n", "demo-ns", "-c", "app", "--tail=100"],
                    ("app logs", "", 0),
                ),
                (
                    [
                        "logs",
                        "demo-pod",
                        "-n",
                        "demo-ns",
                        "-c",
                        "app",
                        "--previous",
                        "--tail=50",
                    ],
                    ("", "previous terminated container not found", 1),
                ),
                (
                    [
                        "get",
                        "pod",
                        "demo-pod",
                        "-n",
                        "demo-ns",
                        "-o",
                        "jsonpath={.spec.initContainers[*].name}",
                    ],
                    ("init-setup", "", 0),
                ),
                (
                    ["logs", "demo-pod", "-n", "demo-ns", "-c", "init-setup", "--tail=100"],
                    ("init logs", "", 0),
                ),
                (
                    [
                        "logs",
                        "demo-pod",
                        "-n",
                        "demo-ns",
                        "-c",
                        "init-setup",
                        "--previous",
                        "--tail=50",
                    ],
                    ("", "container is not terminated", 1),
                ),
                (
                    ["top", "pod", "demo-pod", "-n", "demo-ns", "--containers"],
                    ("resource usage", "", 0),
                ),
                (
                    ["get", "pod", "demo-pod", "-n", "demo-ns", "-o", "jsonpath={.spec.nodeName}"],
                    ("node-a", "", 0),
                ),
                (["describe", "node", "node-a"], ("node describe", "", 0)),
            ]
        )

        self.assertIn("## INIT CONTAINER LOGS ##", output)
        self.assertIn("### Init Container: init-setup ###", output)
        self.assertIn("INFO: No previous terminated init container logs available.", output)

    def test_init_container_query_failure_prints_skip_message(self) -> None:
        output = self._run_with_expected_calls(
            [
                (["get", "pod", "demo-pod", "-n", "demo-ns", "-o", "wide"], ("pod wide", "", 0)),
                (["describe", "pod", "demo-pod", "-n", "demo-ns"], ("pod describe", "", 0)),
                (["get", "pod", "demo-pod", "-n", "demo-ns", "-o", "yaml"], ("pod yaml", "", 0)),
                (
                    [
                        "get",
                        "events",
                        "-n",
                        "demo-ns",
                        "--field-selector",
                        "involvedObject.name=demo-pod",
                        "--sort-by=.lastTimestamp",
                    ],
                    ("event list", "", 0),
                ),
                (
                    ["get", "pod", "demo-pod", "-n", "demo-ns", "-o", "jsonpath={.spec.containers[*].name}"],
                    ("app", "", 0),
                ),
                (
                    ["logs", "demo-pod", "-n", "demo-ns", "-c", "app", "--tail=100"],
                    ("app logs", "", 0),
                ),
                (
                    [
                        "logs",
                        "demo-pod",
                        "-n",
                        "demo-ns",
                        "-c",
                        "app",
                        "--previous",
                        "--tail=50",
                    ],
                    ("", "previous terminated container not found", 1),
                ),
                (
                    [
                        "get",
                        "pod",
                        "demo-pod",
                        "-n",
                        "demo-ns",
                        "-o",
                        "jsonpath={.spec.initContainers[*].name}",
                    ],
                    ("", "forbidden", 1),
                ),
                (
                    ["top", "pod", "demo-pod", "-n", "demo-ns", "--containers"],
                    ("resource usage", "", 0),
                ),
                (
                    ["get", "pod", "demo-pod", "-n", "demo-ns", "-o", "jsonpath={.spec.nodeName}"],
                    ("node-a", "", 0),
                ),
                (["describe", "node", "node-a"], ("node describe", "", 0)),
            ]
        )

        self.assertIn("## INIT CONTAINER LOGS ##", output)
        self.assertIn("forbidden", output)
        self.assertIn(
            "INFO: Skipping init container logs because init container names could not be queried.",
            output,
        )
        self.assertNotIn("### Init Container:", output)


if __name__ == "__main__":
    unittest.main()
