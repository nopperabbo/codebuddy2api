#!/usr/bin/env python3
"""Regression checks for ansible-generator test fixtures."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
TEST_DIR = SKILL_DIR / "test"
PLAYBOOK_DIR = TEST_DIR / "playbooks"
ROLE_DIR = TEST_DIR / "roles" / "sample-role"


class FixtureTemplateTests(unittest.TestCase):
    def test_nginx_playbook_template_exists(self) -> None:
        playbook_text = (PLAYBOOK_DIR / "nginx-tls-playbook.yml").read_text(encoding="utf-8")
        self.assertIn("src: nginx-tls.conf.j2", playbook_text)
        self.assertTrue((PLAYBOOK_DIR / "templates" / "nginx-tls.conf.j2").is_file())

    def test_sample_role_template_exists(self) -> None:
        tasks_text = (ROLE_DIR / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("src: config.j2", tasks_text)
        self.assertTrue((ROLE_DIR / "templates" / "config.j2").is_file())


class RoleMetadataTests(unittest.TestCase):
    def test_role_name_uses_lint_compatible_format(self) -> None:
        meta_text = (ROLE_DIR / "meta" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("role_name: sample_role", meta_text)

    def test_standalone_flag_is_declared(self) -> None:
        meta_text = (ROLE_DIR / "meta" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("standalone: true", meta_text)

    def test_el_platform_uses_schema_safe_version(self) -> None:
        meta_text = (ROLE_DIR / "meta" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("- name: EL", meta_text)
        self.assertIn("- all", meta_text)


class OsVarFallbackTests(unittest.TestCase):
    def test_task_uses_first_found_and_default_vars_file(self) -> None:
        tasks_text = (ROLE_DIR / "tasks" / "main.yml").read_text(encoding="utf-8")
        self.assertIn("lookup('ansible.builtin.first_found', params)", tasks_text)
        self.assertTrue((ROLE_DIR / "vars" / "default.yml").is_file())

    def test_unknown_os_family_uses_fallback_vars_file(self) -> None:
        if shutil.which("ansible-playbook") is None:
            self.skipTest("ansible-playbook is not installed")

        with tempfile.TemporaryDirectory(prefix="ansible-generator-role-test-") as tmp_dir:
            temp_playbook = Path(tmp_dir) / "fallback-vars-smoke.yml"
            temp_playbook.write_text(
                textwrap.dedent(
                    """\
                    ---
                    - name: Verify sample role var fallback
                      hosts: localhost
                      gather_facts: false
                      connection: local
                      vars:
                        ansible_distribution: UnknownDistro
                        ansible_os_family: UnknownFamily
                      roles:
                        - role: sample-role
                    """
                ),
                encoding="utf-8",
            )

            env = os.environ.copy()
            env["ANSIBLE_ROLES_PATH"] = str((TEST_DIR / "roles").resolve())
            cmd = [
                "ansible-playbook",
                str(temp_playbook),
                "-i",
                "localhost,",
                "--tags",
                "always",
            ]
            result = subprocess.run(
                cmd,
                capture_output=True,
                check=False,
                env=env,
                text=True,
            )

            self.assertEqual(
                result.returncode,
                0,
                msg=(
                    "Expected role var loading to succeed for unknown OS family.\n"
                    f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
                ),
            )


if __name__ == "__main__":
    unittest.main()
