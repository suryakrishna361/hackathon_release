"""
Agent 1 — Change Analysis
Reads the git diff and classifies the risk of the candidate branch.
Tools: read_git_diff, read_changed_files, read_commit_messages,
       read_file_contents, compare_env_vars, search_incident_history
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

import anthropic
from agents.base import run_agent_loop, extract_json
from agents.shared_context import ReleaseContext
from tools.git_tools import (
    read_git_diff, read_changed_files, read_commit_messages,
    read_file_contents, compare_env_vars, search_incident_history,
)

MODEL = "claude-haiku-4-5"

SYSTEM_PROMPT = """You are a senior release-engineering AI specialising in change-risk analysis.

Your job:
1. Use the available tools to inspect the diff between the stable (master) branch and
   the candidate branch about to be deployed.
2. Pay special attention to environment-variable changes — these are a common cause of
   silent production failures (service still starts, passes health check, but behaves wrong).
3. Search incident history for similar past patterns.
4. Produce a final risk assessment in the exact JSON schema shown below.

When you have enough evidence, output ONLY this JSON (no other text):
{
  "affected_services": ["list", "of", "service", "names"],
  "risk_level": "low|medium|high|critical",
  "suspected_failure": "one concise sentence describing the most likely failure mode",
  "risk_reasoning": "2-3 sentence explanation of your reasoning",
  "risk_confidence": 0.0
}
risk_confidence is 0.0 – 1.0.
"""

TOOLS = [
    {
        "name": "read_git_diff",
        "description": "Get the full diff between master and candidate branch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "base_branch":      {"type": "string", "default": "master"},
                "candidate_branch": {"type": "string", "default": "candidate"},
            },
        },
    },
    {
        "name": "read_changed_files",
        "description": "List just the file names that changed between branches.",
        "input_schema": {
            "type": "object",
            "properties": {
                "base_branch":      {"type": "string", "default": "master"},
                "candidate_branch": {"type": "string", "default": "candidate"},
            },
        },
    },
    {
        "name": "read_commit_messages",
        "description": "Get recent commit messages on the candidate branch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "branch": {"type": "string", "default": "candidate"},
                "count":  {"type": "integer", "default": 5},
            },
        },
    },
    {
        "name": "read_file_contents",
        "description": "Read a specific file from a branch.",
        "input_schema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string"},
                "branch":    {"type": "string", "default": "candidate"},
            },
            "required": ["file_path"],
        },
    },
    {
        "name": "compare_env_vars",
        "description": "Compare environment variable usage between v1 (master) and v2 (candidate) for a service.",
        "input_schema": {
            "type": "object",
            "properties": {
                "service": {"type": "string", "default": "payment-service"},
            },
        },
    },
    {
        "name": "search_incident_history",
        "description": "Search past deployment incidents for patterns similar to this change.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
        },
    },
]


def _execute_tool(name: str, inputs: dict) -> str:
    dispatch = {
        "read_git_diff":          read_git_diff,
        "read_changed_files":     read_changed_files,
        "read_commit_messages":   read_commit_messages,
        "read_file_contents":     read_file_contents,
        "compare_env_vars":       compare_env_vars,
        "search_incident_history": search_incident_history,
    }
    fn = dispatch.get(name)
    if fn is None:
        return f"Unknown tool: {name}"
    return fn(**inputs)


def run(ctx: ReleaseContext) -> ReleaseContext:
    ctx.log("agent1", "Starting change analysis...")

    client = anthropic.Anthropic()

    user_prompt = (
        "A new candidate branch is ready for deployment. "
        "Analyse the diff, commit messages, env-var changes, and incident history. "
        "Determine the risk level and the most likely failure mode. "
        "Then output your final JSON assessment."
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

    ctx.affected_services  = result.get("affected_services", [])
    ctx.risk_level         = result.get("risk_level", "unknown")
    ctx.suspected_failure  = result.get("suspected_failure", "")
    ctx.risk_reasoning     = result.get("risk_reasoning", "")
    ctx.risk_confidence    = float(result.get("risk_confidence", 0.0))

    ctx.log("agent1", f"Risk level: {ctx.risk_level} | Confidence: {ctx.risk_confidence:.0%}")
    ctx.log("agent1", f"Suspected failure: {ctx.suspected_failure}")
    return ctx
