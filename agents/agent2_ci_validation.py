"""
Agent 2 — CI & Environment Validation
Reads GitHub Actions test results then checks env-var alignment and deployment config.
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import anthropic
from agents.base import run_agent_loop, extract_json
from agents.shared_context import ReleaseContext
from tools.ci_tools import check_env_var_coverage, compare_configs
from tools.git_tools import compare_env_vars
from tools.github_tools import get_latest_commit, wait_for_workflow, get_workflow_jobs

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """You are a CI/CD validation AI. Your job is to gate deployments by verifying
that GitHub Actions tests passed and that environment configuration is consistent.

Steps:
1. Call get_latest_commit to get the candidate branch's latest commit SHA.
2. Call wait_for_workflow with that SHA to wait for GitHub Actions to finish.
3. Call get_workflow_jobs with the run_id to see per-job pass/fail details.
4. Call check_env_var_coverage and compare_configs to check configuration alignment.
5. Call compare_env_vars to find renamed or removed env vars.

Output ONLY this JSON when done:
{
  "tests_passed": true,
  "config_compatible": true,
  "missing_env_vars": [],
  "renamed_env_vars": [],
  "validation_warnings": [],
  "github_actions_conclusion": "success"
}

- tests_passed: true only if GitHub Actions conclusion is "success"
- github_actions_conclusion: the raw conclusion from GitHub ("success", "failure", etc.)
- config_compatible: are the deployment configs consistent?
- missing_env_vars: env vars present in stable deploy but absent from candidate
- renamed_env_vars: list of "OLD → NEW" strings
- validation_warnings: any other concerns
"""

TOOLS = [
    {
        "name": "get_latest_commit",
        "description": "Get the latest commit SHA on the candidate branch from GitHub.",
        "input_schema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "default": "candidate"},
            },
        },
    },
    {
        "name": "wait_for_workflow",
        "description": "Wait for GitHub Actions CI workflow to complete for a given commit SHA. Returns status and conclusion.",
        "input_schema": {
            "type": "object",
            "properties": {
                "commit_sha": {"type": "string"},
                "timeout_seconds": {"type": "integer", "default": 300},
            },
            "required": ["commit_sha"],
        },
    },
    {
        "name": "get_workflow_jobs",
        "description": "Get per-job pass/fail details for a completed workflow run.",
        "input_schema": {
            "type": "object",
            "properties": {
                "run_id": {"type": "integer"},
            },
            "required": ["run_id"],
        },
    },
    {
        "name": "check_env_var_coverage",
        "description": "Check which env vars the candidate code reads and whether tests cover them.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "default": "payment-service"},
            },
        },
    },
    {
        "name": "compare_configs",
        "description": "Compare Docker Compose env vars for stable vs candidate deployment.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "default": "payment-service"},
            },
        },
    },
    {
        "name": "compare_env_vars",
        "description": "Compare os.getenv() calls between master and candidate source code.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "default": "payment-service"},
            },
        },
    },
]


def _execute_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "get_latest_commit":      get_latest_commit,
        "wait_for_workflow":      wait_for_workflow,
        "get_workflow_jobs":      get_workflow_jobs,
        "check_env_var_coverage": check_env_var_coverage,
        "compare_configs":        compare_configs,
        "compare_env_vars":       compare_env_vars,
    }
    fn = dispatch.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return str(fn(**inputs))


def run(ctx: ReleaseContext) -> ReleaseContext:
    ctx.log("agent2", "Starting CI & environment validation...")

    client = anthropic.Anthropic()

    services    = ctx.affected_services or ["payment-service"]
    user_prompt = (
        f"Validate the candidate deployment for services: {services}. "
        f"Agent 1 assessed risk as '{ctx.risk_level}' with suspected failure: '{ctx.suspected_failure}'. "
        "First check GitHub Actions results for the candidate branch commit, "
        "then verify env var coverage and deployment config alignment. "
        "Output your final JSON validation report."
    )

    raw = run_agent_loop(
        client=client,
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        tools=TOOLS,
        tool_executor=_execute_tool,
    )

    result = extract_json(raw)

    ctx.tests_passed                = result.get("tests_passed", False)
    ctx.config_compatible           = result.get("config_compatible", True)
    ctx.missing_env_vars            = result.get("missing_env_vars", [])
    ctx.renamed_env_vars            = result.get("renamed_env_vars", [])
    ctx.validation_warnings         = result.get("validation_warnings", [])
    ctx.github_actions_conclusion   = result.get("github_actions_conclusion", "unknown")

    ctx.log("agent2", f"GitHub Actions: {ctx.github_actions_conclusion} | Tests passed: {ctx.tests_passed} | Config compatible: {ctx.config_compatible}")
    if ctx.validation_warnings:
        ctx.log("agent2", f"Warnings: {ctx.validation_warnings}", level="warn")
    return ctx
