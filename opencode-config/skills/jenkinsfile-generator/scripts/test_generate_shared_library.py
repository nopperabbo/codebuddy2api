#!/usr/bin/env python3
"""Regression tests for generate_shared_library.py."""

from pathlib import Path
import sys
import tempfile
import unittest


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from generate_shared_library import SharedLibraryGenerator  # noqa: E402


class SharedLibraryDeployTemplateRegressionTests(unittest.TestCase):
    """Ensure generated deploy helper remains Kubernetes-safe."""

    def _render_deploy_template(self) -> str:
        with tempfile.TemporaryDirectory() as temp_dir:
            generator = SharedLibraryGenerator(
                name="example-lib",
                package="org.example",
                output_dir=temp_dir,
            )
            generator.generate()
            deploy_path = Path(temp_dir) / "example-lib" / "vars" / "deployApp.groovy"
            return deploy_path.read_text(encoding="utf-8")

    def test_deployment_name_uses_job_base_name_and_dns_sanitization(self):
        text = self._render_deploy_template()

        self.assertIn("config.get('deploymentName', env.JOB_BASE_NAME ?: '')", text)
        self.assertNotIn("config.get('deploymentName', env.JOB_NAME)", text)
        self.assertIn(".replaceAll(/[^a-z0-9-]/, '-')", text)
        self.assertIn(".replaceAll(/-+/, '-')", text)
        self.assertIn(".replaceAll(/^-|-$/, '')", text)
        self.assertIn("if (deploymentName.length() > 63)", text)
        self.assertIn(
            "deploymentName is required and must resolve to a valid Kubernetes deployment name",
            text,
        )

    def test_rollout_command_uses_quoted_env_variables(self):
        text = self._render_deploy_template()

        self.assertIn("withEnv([", text)
        self.assertIn("\"KUBE_NAMESPACE=${namespace}\"", text)
        self.assertIn("\"DEPLOYMENT_NAME=${deploymentName}\"", text)
        self.assertIn("\"MANIFESTS_PATH=${manifests}\"", text)
        self.assertIn("set -euo pipefail", text)
        self.assertIn("kubectl apply -f \"$MANIFESTS_PATH\" -n \"$KUBE_NAMESPACE\"", text)
        self.assertIn(
            "kubectl rollout status \"deployment/$DEPLOYMENT_NAME\" -n \"$KUBE_NAMESPACE\" --timeout=300s",
            text,
        )
        self.assertNotIn("deployment/${deploymentName}", text)


if __name__ == "__main__":
    unittest.main()
