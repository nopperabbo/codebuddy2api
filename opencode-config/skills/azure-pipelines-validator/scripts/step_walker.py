#!/usr/bin/env python3
"""Shared traversal helpers for Azure Pipelines step scanning."""

from __future__ import annotations

import re
from typing import Any, Dict, Iterator, List, Tuple

_TEMPLATE_EXPR_KEY = re.compile(r"^\s*\$\{\{.*\}\}\s*$")
_STEP_KEYS = {
    "task",
    "script",
    "bash",
    "pwsh",
    "powershell",
    "checkout",
    "download",
    "downloadBuild",
    "getPackage",
    "publish",
    "template",
    "reviewApp",
}
_DEPLOYMENT_STRATEGIES = ("runOnce", "rolling", "canary")
_DEPLOYMENT_PHASES = ("preDeploy", "deploy", "routeTraffic", "postRouteTraffic")


def _get_mapping_value(node: Dict[str, Any], key: str) -> Any:
    """Fetch mapping value while tolerating YAML 1.1 bool coercion for `on`."""
    if key in node:
        return node[key]
    if key == "on" and True in node:
        return node[True]
    return None


def _is_template_expression_key(key: Any) -> bool:
    if not isinstance(key, str):
        return False
    return _TEMPLATE_EXPR_KEY.match(key) is not None


def _iter_template_payloads(node: Dict[str, Any]) -> Iterator[Any]:
    for key, value in node.items():
        if _is_template_expression_key(key):
            yield value


def _is_step_like(node: Dict[str, Any]) -> bool:
    return any(step_key in node for step_key in _STEP_KEYS)


def _iter_nested_step_payload(payload: Any, context: str) -> Iterator[Tuple[Dict[str, Any], str]]:
    if isinstance(payload, list):
        yield from _iter_step_list(payload, context)
        return

    if not isinstance(payload, dict):
        return

    if _is_step_like(payload):
        yield payload, context

    nested_steps = payload.get("steps")
    if isinstance(nested_steps, list):
        yield from _iter_step_list(nested_steps, context)

    for nested_payload in _iter_template_payloads(payload):
        yield from _iter_nested_step_payload(nested_payload, context)


def _iter_step_list(steps: List[Any], context: str) -> Iterator[Tuple[Dict[str, Any], str]]:
    if not isinstance(steps, list):
        return

    for step in steps:
        if not isinstance(step, dict):
            continue

        for conditional_payload in _iter_template_payloads(step):
            yield from _iter_nested_step_payload(conditional_payload, context)

        if _is_step_like(step):
            yield step, context

        nested_steps = step.get("steps")
        if isinstance(nested_steps, list):
            yield from _iter_step_list(nested_steps, context)


def _iter_strategy_steps(
    strategy_node: Dict[str, Any], job_context: str, strategy_type: str
) -> Iterator[Tuple[Dict[str, Any], str]]:
    for phase in _DEPLOYMENT_PHASES:
        phase_data = _get_mapping_value(strategy_node, phase)
        yield from _iter_nested_step_payload(phase_data, f"{job_context} {strategy_type}.{phase}")

    on_data = _get_mapping_value(strategy_node, "on")
    if isinstance(on_data, dict):
        success_data = _get_mapping_value(on_data, "success")
        yield from _iter_nested_step_payload(success_data, f"{job_context} {strategy_type}.on.success")

        failure_data = _get_mapping_value(on_data, "failure")
        yield from _iter_nested_step_payload(failure_data, f"{job_context} {strategy_type}.on.failure")

        for conditional_payload in _iter_template_payloads(on_data):
            yield from _iter_nested_step_payload(
                conditional_payload, f"{job_context} {strategy_type}.on"
            )


def _iter_job_entries(jobs: Any) -> Iterator[Tuple[Dict[str, Any], str]]:
    if isinstance(jobs, list):
        for job in jobs:
            yield from _iter_job_entries(job)
        return

    if not isinstance(jobs, dict):
        return

    conditional_payloads = list(_iter_template_payloads(jobs))
    for payload in conditional_payloads:
        yield from _iter_job_entries(payload)

    job_name = jobs.get("job") or jobs.get("deployment")
    if not job_name:
        return

    job_context = f"job '{job_name}'"
    if isinstance(jobs.get("steps"), list):
        yield from _iter_step_list(jobs["steps"], job_context)

    strategy = jobs.get("strategy")
    if isinstance(strategy, dict):
        for strategy_type in _DEPLOYMENT_STRATEGIES:
            strategy_node = strategy.get(strategy_type)
            if isinstance(strategy_node, dict):
                yield from _iter_strategy_steps(strategy_node, job_context, strategy_type)


def _iter_stage_entries(stages: Any) -> Iterator[Tuple[Dict[str, Any], str]]:
    if isinstance(stages, list):
        for stage in stages:
            yield from _iter_stage_entries(stage)
        return

    if not isinstance(stages, dict):
        return

    conditional_payloads = list(_iter_template_payloads(stages))
    for payload in conditional_payloads:
        yield from _iter_stage_entries(payload)

    if isinstance(stages.get("jobs"), list):
        yield from _iter_job_entries(stages["jobs"])


def iter_steps(config: Any) -> Iterator[Tuple[Dict[str, Any], str]]:
    """Yield (step, context) pairs from standard and conditional/deployment blocks."""
    if not isinstance(config, dict):
        return

    if isinstance(config.get("steps"), list):
        yield from _iter_step_list(config["steps"], "pipeline")

    if isinstance(config.get("jobs"), list):
        yield from _iter_job_entries(config["jobs"])

    if isinstance(config.get("stages"), list):
        yield from _iter_stage_entries(config["stages"])
