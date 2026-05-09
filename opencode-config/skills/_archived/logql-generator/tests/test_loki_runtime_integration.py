#!/usr/bin/env python3
"""Runtime Loki integration tests for logql-generator query regressions."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import unittest
from urllib import error, parse, request


RUN_MODE = os.getenv("RUN_LOKI_RUNTIME_TESTS", "auto").strip().lower()
LOKI_IMAGE = os.getenv("LOKI_IMAGE", "grafana/loki:3.6.2").strip()
STARTUP_TIMEOUT_SECONDS = int(os.getenv("LOKI_STARTUP_TIMEOUT_SECONDS", "60"))
QUERY_TIMEOUT_SECONDS = int(os.getenv("LOKI_QUERY_TIMEOUT_SECONDS", "25"))

_REQUIRE_VALUES = {"1", "true", "yes", "required"}
_SKIP_VALUES = {"0", "false", "no", "off", "skip"}


class LokiRuntimeIntegrationTests(unittest.TestCase):
    """Validate key query examples against a real ephemeral Loki runtime."""

    container_name: str | None = None
    base_url: str | None = None

    @staticmethod
    def _docker_available() -> bool:
        if shutil.which("docker") is None:
            return False
        try:
            subprocess.run(
                ["docker", "info"],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except (OSError, subprocess.CalledProcessError):
            return False
        return True

    @staticmethod
    def _reserve_host_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    @classmethod
    def _stop_container(cls) -> None:
        if not cls.container_name:
            return
        subprocess.run(
            ["docker", "rm", "-f", cls.container_name],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        cls.container_name = None
        cls.base_url = None

    @classmethod
    def setUpClass(cls) -> None:
        if RUN_MODE in _SKIP_VALUES:
            raise unittest.SkipTest(
                "Runtime Loki tests skipped by RUN_LOKI_RUNTIME_TESTS."
            )

        docker_ready = cls._docker_available()
        if RUN_MODE in _REQUIRE_VALUES and not docker_ready:
            raise RuntimeError(
                "RUN_LOKI_RUNTIME_TESTS requires Docker, but Docker is unavailable."
            )
        if RUN_MODE not in _REQUIRE_VALUES and not docker_ready:
            raise unittest.SkipTest(
                "Docker unavailable; skipping runtime Loki tests (auto mode)."
            )

        host_port = cls._reserve_host_port()
        cls.container_name = f"logql-generator-loki-{os.getpid()}-{int(time.time())}"
        cls.base_url = f"http://127.0.0.1:{host_port}"

        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "-d",
                    "--rm",
                    "--name",
                    cls.container_name,
                    "-p",
                    f"{host_port}:3100",
                    LOKI_IMAGE,
                    "-config.file=/etc/loki/local-config.yaml",
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
            cls._wait_until_ready()
            cls._push_sample_logs()
        except Exception:
            cls._stop_container()
            raise

    @classmethod
    def tearDownClass(cls) -> None:
        cls._stop_container()

    @classmethod
    def _wait_until_ready(cls) -> None:
        assert cls.base_url is not None
        ready_url = f"{cls.base_url}/ready"
        deadline = time.time() + STARTUP_TIMEOUT_SECONDS
        last_error: str | None = None

        while time.time() < deadline:
            try:
                with request.urlopen(ready_url, timeout=4) as response:
                    body = response.read().decode("utf-8", errors="ignore").lower()
                    if response.status == 200 and "ready" in body:
                        return
            except error.HTTPError as exc:  # pragma: no cover - retry loop
                try:
                    exc.read()
                finally:
                    exc.close()
                last_error = f"HTTP {exc.code}"
            except Exception as exc:  # pragma: no cover - retry loop
                last_error = str(exc)
            time.sleep(1)

        raise RuntimeError(f"Loki did not become ready in time: {last_error}")

    @classmethod
    def _push_sample_logs(cls) -> None:
        assert cls.base_url is not None
        now_ns = time.time_ns()
        # Keep log lines within a recent 5m range window for rate()/bytes_over_time().
        samples = {
            "streams": [
                {
                    "stream": {"app": "api", "job": "http-server"},
                    "values": [
                        [str(now_ns - 90_000_000_000), '{"status_code":200,"duration":0.12,"level":"info"}'],
                        [str(now_ns - 60_000_000_000), '{"status_code":500,"duration":1.42,"level":"error"}'],
                        [str(now_ns - 30_000_000_000), '{"status_code":500,"duration":0.98,"level":"error"}'],
                    ],
                },
                {
                    "stream": {"app": "billing", "job": "http-server"},
                    "values": [
                        [str(now_ns - 85_000_000_000), '{"status_code":200,"duration":0.10,"level":"info"}'],
                        [str(now_ns - 55_000_000_000), '{"status_code":404,"duration":0.23,"level":"warn"}'],
                        [str(now_ns - 25_000_000_000), '{"status_code":500,"duration":1.33,"level":"error"}'],
                    ],
                },
            ]
        }
        payload = json.dumps(samples, separators=(",", ":")).encode("utf-8")
        req = request.Request(
            f"{cls.base_url}/loki/api/v1/push",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with request.urlopen(req, timeout=10) as response:
            if response.status != 204:
                raise RuntimeError(f"Unexpected Loki push status code: {response.status}")

    def _query(self, query: str) -> list[dict]:
        assert self.base_url is not None
        url = f"{self.base_url}/loki/api/v1/query?{parse.urlencode({'query': query})}"
        req = request.Request(url, method="GET")
        try:
            with request.urlopen(req, timeout=10) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="ignore")
            raise AssertionError(f"Loki query failed ({exc.code}): {body}") from exc

        self.assertEqual(payload.get("status"), "success", msg=str(payload))
        return payload.get("data", {}).get("result", [])

    def _query_until_non_empty(self, query: str) -> list[dict]:
        deadline = time.time() + QUERY_TIMEOUT_SECONDS
        last_error: Exception | None = None
        last_result: list[dict] = []

        while time.time() < deadline:
            try:
                last_result = self._query(query)
                if last_result:
                    return last_result
            except Exception as exc:  # pragma: no cover - retry loop
                last_error = exc
            time.sleep(1)

        if last_error is not None:
            raise AssertionError(f"Query did not stabilize: {last_error}") from last_error
        raise AssertionError(f"Query returned no results within timeout: {query}")

    def test_ratio_against_total_with_on_group_left_executes(self) -> None:
        query = (
            'sum by (status_code) (rate({app="api"} | json [5m]))'
            " / on() group_left "
            'sum(rate({app="api"}[5m]))'
        )
        result = self._query_until_non_empty(query)
        self.assertGreaterEqual(len(result), 2)
        for series in result:
            self.assertIn("status_code", series.get("metric", {}))

    def test_many_to_one_ratio_with_group_left_executes(self) -> None:
        query = (
            'sum by (app, status_code) (rate({job="http-server"} | json [5m]))'
            " / on(app) group_left "
            'sum by (app) (rate({job="http-server"} | json [5m]))'
        )
        result = self._query_until_non_empty(query)
        apps = set()
        for series in result:
            metric = series.get("metric", {})
            self.assertIn("app", metric)
            self.assertIn("status_code", metric)
            apps.add(metric["app"])
        self.assertIn("api", apps)
        self.assertIn("billing", apps)

    def test_bytes_over_time_executes_without_unwrap(self) -> None:
        query = 'bytes_over_time({app="api"}[5m])'
        result = self._query_until_non_empty(query)
        self.assertTrue(any(series.get("metric", {}).get("app") == "api" for series in result))


if __name__ == "__main__":
    unittest.main()
