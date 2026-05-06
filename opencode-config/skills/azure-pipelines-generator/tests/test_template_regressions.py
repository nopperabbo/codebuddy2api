#!/usr/bin/env python3
"""Regression tests for azure-pipelines-generator template safeguards."""

from pathlib import Path
import re
import unittest


SKILL_DIR = Path(__file__).resolve().parent.parent
DEPLOY_TEMPLATE = SKILL_DIR / "examples" / "templates" / "deploy-template.yml"
TEMPLATE_USAGE = SKILL_DIR / "examples" / "template-usage.yml"


class DeployTemplateRegressionTests(unittest.TestCase):
    """Ensure stage dependencies and approval reminder behavior stay safe."""

    def test_depends_on_is_conditionally_inserted(self):
        text = DEPLOY_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn(
            "${{ if gt(length(parameters.dependsOn), 0) }}:",
            text,
            "dependsOn must be conditionally inserted when non-empty.",
        )
        self.assertNotRegex(
            text,
            r"(?m)^ {4}dependsOn:\s+\$\{\{\s*parameters\.dependsOn\s*\}\}\s*$",
            "unconditional dependsOn reintroduces parallel-stage regression risk.",
        )

    def test_approval_reminder_is_explicit_and_backward_compatible(self):
        text = DEPLOY_TEMPLATE.read_text(encoding="utf-8")
        self.assertRegex(text, r"- name:\s+approvalReminder")
        self.assertRegex(text, r"- name:\s+approvalRequired")
        self.assertIn(
            "Approval Reminder (Informational Only)",
            text,
            "approval reminder display text must explicitly indicate informational-only behavior.",
        )
        self.assertIn(
            "YAML does not enforce approvals.",
            text,
            "template must clarify approvals are configured in environment checks.",
        )


class TemplateUsageRegressionTests(unittest.TestCase):
    """Ensure template consumers use safe defaults and updated parameter names."""

    def test_staging_uses_sequential_default_without_depends_on(self):
        text = TEMPLATE_USAGE.read_text(encoding="utf-8")
        match = re.search(
            r"environment:\s*'staging'(?P<body>[\s\S]*?)\n\s*# Deploy to production",
            text,
        )
        self.assertIsNotNone(match, "staging template usage block not found.")
        body = match.group("body")
        self.assertNotRegex(
            body,
            r"(?m)^\s*dependsOn:",
            "staging block should omit dependsOn to use sequential stage default.",
        )
        self.assertRegex(body, r"approvalReminder:\s*false")

    def test_production_keeps_explicit_dependency_and_new_parameter(self):
        text = TEMPLATE_USAGE.read_text(encoding="utf-8")
        match = re.search(r"environment:\s*'production'(?P<body>[\s\S]*)$", text)
        self.assertIsNotNone(match, "production template usage block not found.")
        body = match.group("body")
        self.assertRegex(body, r"dependsOn:\s*\n\s*-\s*Deploy_staging")
        self.assertRegex(body, r"approvalReminder:\s*true")
        self.assertNotIn("approvalRequired:", text)


if __name__ == "__main__":
    unittest.main()
